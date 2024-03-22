# encoding = utf-8

# Author: Alexandre Demeyer <letmer00t@gmail.com>
# Inspired by: Donald Murchison

import globals
import sys
import datetime
import hashlib
import random
from common import LoggerFile, Backlog

def process_event(helper, *args, **kwargs):
    """
    # IMPORTANT
    # Do not remove the anchor macro:start and macro:end lines.
    # These lines are used to generate sample code. If they are
    # removed, the sample code will not be updated when configurations
    # are updated.

    [sample_code_macro:start]

    # The following example gets and sets the log level
    helper.set_log_level(helper.log_level)

    # The following example gets account information
    user_account = helper.get_user_credential("<account_name>")

    # The following example gets the alert action parameters and prints them to the log
    batch_name = helper.get_param("batch_name")
    helper.log_info("batch_name={}".format(batch_name))
    batch_priority = helper.get_param("batch_priority")
    helper.log_info("batch_priority={}".format(batch_priority))
    savedsearch_field_name = helper.get_param("savedsearch_field_name")
    helper.log_info("savedsearch_field_name={}".format(savedsearch_field_name))

    app_field_name = helper.get_param("app_field_name")
    helper.log_info("app_field_name={}".format(app_field_name))

    earliest_time_field_name = helper.get_param("earliest_time_field_name")
    helper.log_info("earliest_time_field_name={}".format(earliest_time_field_name))

    latest_time_field_name = helper.get_param("latest_time_field_name")
    helper.log_info("latest_time_field_name={}".format(latest_time_field_name))


    # The following example adds two sample events ("hello", "world")
    # and writes them to Splunk
    # NOTE: Call helper.writeevents() only once after all events
    # have been added
    helper.addevent("hello", sourcetype="sample_sourcetype")
    helper.addevent("world", sourcetype="sample_sourcetype")
    helper.writeevents(index="summary", host="localhost", source="localhost")

    # The following example gets the events that trigger the alert
    events = helper.get_events()
    for event in events:
        helper.log_info("event={}".format(event))

    # helper.settings is a dict that includes environment configuration
    # Example usage: helper.settings["server_uri"]
    helper.log_info("server_uri={}".format(helper.settings["server_uri"]))
    [sample_code_macro:end]
    """

    globals.initialize_globals()

    # Set the current LOG level
    logger = helper._logger
    logger_file = LoggerFile(logger, "CAA-AHTTTB")
    helper.log_info("[CAA-ABTTB-001] LOG level to: " + helper.log_level)
    helper.set_log_level(helper.log_level)

    # Build the context around the Splunk instance
    spl_token = helper.settings["sessionKey"] if "sessionKey" in helper.settings else helper.settings["session_key"]
    sid = helper.settings["sid"]
    globals.log_context = "[sid={0}]".format(sid)
    # Default app is the current one
    app = "TA-detection-backfill"

    # Initialize the backlog
    lookup_file_name = "detection_backfill_healthcheck_backlog.csv"
    lookup_headers= ["hc_uid", "hc_created_time","hc_created_author", "batch_name", "batch_priority", "orig_exec_time", "orig_search_id", "app", "savedsearch_name", "orig_search_et", "orig_search_lt", "orig_scan_count", "orig_event_count", "orig_result_count"]
    backlog = Backlog(name="Backlog - Healthcheck", lookup_file_name=lookup_file_name ,lookup_headers=lookup_headers ,spl_token=spl_token ,logger=logger)

    # Initialize batch
    batch_priority = int(helper.get_param("batch_priority"))

    # Prepare all the tasks to be added
    tasks = []

    # Get the information from the events and process them
    events = helper.get_events()

    for event in events:
        
        logger_file.debug("002","Process this event: " + str(event))

        # Analyze the event and validate the structure

        # Splunk makes a bunch of dumb empty multivalue fields
        # replace value by multivalue if required
        logger_file.debug("010","Row before pre-processing: " + str(event))
        for key, value in event.items():
            if not key.startswith("__mv_") and "__mv_" + key in event and event["__mv_" + key] not in [None, '']:
                event[key] = [e[1:len(e) - 1] for e in event["__mv_" + key].split(";")]
        # we filter those out here
        event = {key: value for key, value in event.items() if not key.startswith("__mv_") and key not in ["rid"]}
        logger_file.debug("011","Row after pre-processing: " + str(event))

        # Check that the event does have the required parameters
        expected_fields = ["exec_time", "search_id", "app", "savedsearch_name", "search_et", "search_lt", "scan_count", "event_count", "result_count"]
        for p in expected_fields:
            if p not in event:
                logger_file.error("015","A required field wasn't found in the event: '{field}'. Expected fields are: {expected_fields}. Skipped the processing of the event: {event}".format(field=p,expected_fields=expected_fields,event=str(event)))

        # Build the task for the backlog
        now = datetime.datetime.now().timestamp()

        orig_sid = event["search_id"].replace("'","")

        # Initialize backfill
        hc_uid = hashlib.sha256((orig_sid+str(now)+str(random.randrange(0,1000000000))).encode('utf-8')).hexdigest()[:16]

        # Initialize task
        task = {
            "hc_uid": hc_uid,
            "hc_created_time": now,
            "hc_created_author": helper.settings["owner"],
            "batch_priority": batch_priority,
            "batch_name": "Healthcheck job for orig SID: "+orig_sid,
            "orig_exec_time": int(event["exec_time"]),
            "orig_search_id": orig_sid,
            "app": event["app"],
            "savedsearch_name": event["savedsearch_name"],
            "orig_search_et": event["search_et"],
            "orig_search_lt": event["search_lt"],
            "orig_scan_count": event["scan_count"],
            "orig_event_count": event["event_count"],
            "orig_result_count": event["result_count"]
        }

        tasks.append(task)
    
    # Add tasks to the backlog
    backlog.add(tasks)

    return 0