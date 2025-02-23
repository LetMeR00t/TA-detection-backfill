# encoding = utf-8

# Author: Alexandre Demeyer <letmer00t@gmail.com>
# Inspired by: Donald Murchison

import uuid
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
    logger_file = LoggerFile(logger, "CAA-ABTTB")
    helper.log_info("[CAA-ABTTB-001] LOG level to: " + helper.log_level)
    helper.set_log_level(helper.log_level)

    # Build the context around the Splunk instance
    sid = helper.settings["sid"]
    globals.log_context = "[sid={0}]".format(sid)

    # Get parameters
    app_field_name = helper.get_param("app_field_name")
    savedsearch_field_name = helper.get_param("savedsearch_field_name")
    dispatch_time_field_name = helper.get_param("dispatch_time_field_name")
    spl_code_injection_id = helper.get_param("spl_code_injection")
    trigger = helper.get_param("trigger")

    # Get backlog
    spl_token = helper.settings["sessionKey"] if "sessionKey" in helper.settings else helper.settings["session_key"]

    lookup_file_name = "detection_backfill_rerun_backlog.csv"
    lookup_headers = ["bf_uid","bf_created_time","bf_created_author","batch_name","batch_priority","bf_batch_id","bf_spl_code_injection_id","bf_trigger","app","savedsearch","dispatch_time"]
    backlog = Backlog(name="Backlog - Rerun", lookup_file_name=lookup_file_name ,lookup_headers=lookup_headers ,spl_token=spl_token ,logger=logger)

    # Get the information from the events and process them
    events = helper.get_events()

    # Initialize batch
    batch_name = helper.get_param("batch_name")
    batch_priority = int(helper.get_param("batch_priority"))
    bf_batch_id = str(uuid.uuid4())

    tasks = []

    for event in events:
        
        logger_file.debug("002","Process this event: " + str(event))

        now = datetime.datetime.now().timestamp()

        # Initialize backfill
        bf_uid = str(uuid.uuid4())

        # Initialize task
        task = {"bf_uid": bf_uid, "batch_name": batch_name, "batch_priority": batch_priority, "bf_batch_id": bf_batch_id, "bf_spl_code_injection_id": spl_code_injection_id, "bf_trigger": trigger, "bf_created_time": now, "bf_created_author": helper.settings["owner"]}

        # Enrich task with the event values
        if app_field_name in event:
            task["app"] = event[app_field_name]
        else:
            logger_file.error("010","An issue was found with the task: Field name '{0}' doesn't exist in the event".format(app_field_name))
            sys.exit(10)
        if savedsearch_field_name in event:
            task["savedsearch"] = event[savedsearch_field_name]
        else:
            logger_file.error("010","An issue was found with the task: Field name '{0}' doesn't exist in the event".format(savedsearch_field_name))
            sys.exit(11)
        if dispatch_time_field_name in event:
            task["dispatch_time"] = event[dispatch_time_field_name]
        else:
            logger_file.error("010","An issue was found with the task: Field name '{0}' doesn't exist in the event".format(dispatch_time_field_name))
            sys.exit(12)

        tasks.append(task)
    
    # Add tasks to the backlog
    backlog.add(tasks)

    return 0
