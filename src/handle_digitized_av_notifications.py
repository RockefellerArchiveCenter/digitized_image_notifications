#!/usr/bin/env python3

import json
import logging
import traceback
from os import environ

import boto3
import urllib3

http = urllib3.PoolManager()

logger = logging.getLogger()
logger.setLevel(logging.INFO)


full_config_path = f"/{environ.get('ENV')}/{environ.get('APP_CONFIG_PATH')}"


def parse_attributes(attributes):
    """Parses attributes from messages."""
    color_name = '#ff0000' if attributes['outcome']['Value'] == 'FAILURE' else '#008000'
    format = attributes['format']['Value']
    refid = attributes['refid']['Value']
    service = attributes['service']['Value']
    outcome = attributes['outcome']['Value'].lower()
    message = attributes.get('message', {}).get('Value')
    return color_name, format, refid, service, outcome, message


def structure_teams_message(color_name, title, message, facts):
    """Structures Teams message using arguments."""
    notification = {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": color_name,
        "summary": message if message else 'Summary',
        "sections": [{
            "activityTitle": title,
            "text": message if message else 'Summary',
            "facts": [{"name": k, "value": v} for k, v in facts.items()]
        }]}
    return json.dumps(notification).encode('utf-8')


def send_teams_message(message, url):
    """Delivers message to Teams channel endpoint."""
    response = http.request('POST', url, body=message)
    logger.info('Status Code: {}'.format(response.status))
    logger.info('Response: {}'.format(response.data))


def get_config(ssm_parameter_path):
    """Fetch config values from Parameter Store.

    Args:
        ssm_parameter_path (str): Path to parameters

    Returns:
        configuration (dict): all parameters found at the supplied path.
    """
    configuration = {}
    try:
        ssm_client = boto3.client(
            'ssm', region_name=environ.get(
                'AWS_DEFAULT_REGION', 'us-east-1'))

        param_details = ssm_client.get_parameters_by_path(
            Path=ssm_parameter_path,
            Recursive=False,
            WithDecryption=True)

        for param in param_details.get('Parameters', []):
            param_path_array = param.get('Name').split("/")
            section_position = len(param_path_array) - 1
            section_name = param_path_array[section_position]
            configuration[section_name] = param.get('Value')

    except BaseException:
        print("Encountered an error loading config from SSM.")
        traceback.print_exc()
    finally:
        return configuration


def lambda_handler(event, context):
    """Main handler for function."""
    logger.info("Message received.")

    config = get_config(full_config_path)

    title = event['Records'][0]['Sns']['Message']
    attributes = event['Records'][0]['Sns']['MessageAttributes']
    color_name, format, refid, service, outcome, message = parse_attributes(
        attributes)
    structured_message = structure_teams_message(
        color_name,
        title,
        message,
        {'Service': service, 'Outcome': outcome, 'Format': format, 'RefID': refid})
    decrypted_url = config.get('TEAMS_URL')
    send_teams_message(structured_message, decrypted_url)
