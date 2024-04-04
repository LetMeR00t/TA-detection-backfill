
# encoding = utf-8

# Author: Alexandre Demeyer <letmer00t@gmail.com>

import globals
import sys
import datetime
import tzlocal
import json
import splunklib.client as client
from common import Settings, LoggerFile, Backlog

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
    logger_file = LoggerFile(logger, "CAA-RHMS")
    helper.log_info("[CAA-RTNB-000] LOG level to: " + helper.log_level)
    helper.set_log_level(helper.log_level)

    # Build the context around the Splunk instance
    owner = helper.settings["owner"]
    spl_token = helper.settings["sessionKey"] if "sessionKey" in helper.settings else helper.settings["session_key"]
    sid = helper.settings["sid"]
    globals.log_context = "[sid={0}]".format(sid)

    # Default app is the current one
    app = "TA-detection-backfill"

    # Try to connect to the Splunk API for the Detection Backfill app
    logger_file.debug("001","Connecting to Splunk API with the app context set to {app}...".format(app=app))
    try:
        spl_detection_backfill = client.connect(app=app, owner=owner, token=spl_token)
        logger_file.debug("002","Connected to Splunk API successfully")
    except Exception as e:
        logger_file.error("003","{}".format(e.msg))

    # Get settings
    configuration = Settings(spl_detection_backfill, helper.settings, logger)

    # Get backlog
    lookup_file_name = "detection_backfill_healthcheck_backlog.csv"
    lookup_headers= ["hc_uid", "hc_created_time","hc_created_author", "batch_name", "batch_priority", "orig_exec_time", "orig_search_id", "app", "savedsearch_name", "orig_search_et", "orig_search_lt", "orig_scan_count", "orig_event_count", "orig_result_count"]
    backlog = Backlog(name="Backlog - Healthcheck", lookup_file_name=lookup_file_name ,lookup_headers=lookup_headers ,spl_token=spl_token ,logger=logger)

    # Get the information from the events and process them
    events = helper.get_events()
    counter = 0
    for event in events:
        counter += 1

    logger_file.info("004","Counter set to {0}. Will process the first {0} elements of the backlog...".format(str(counter)))

    # Get next task
    tasks = backlog.next_tasks(counter)

    if tasks == []:
        logger_file.info("005","Backlog is empty, nothing to rerun.")

    # Savedsearch cache
    savedsearches = {}

    if len(tasks) > 0:

        for task in tasks:

            ## Get the savedsearch and dispatch again the search
            hc_uid = task["hc_uid"]
            hc_created_time = task["hc_created_time"]
            hc_created_author = task["hc_created_author"]
            timestamp_origin = int(task["orig_exec_time"])
            timestamp_origin_readeable = datetime.datetime.fromtimestamp(timestamp_origin,tz=tzlocal.get_localzone()).strftime("%c %z")
            sid_origin = task["orig_search_id"]
            app = task["app"]
            savedsearch_name = task["savedsearch_name"]
            dispatch_earliest = task["orig_search_et"]
            dispatch_latest = task["orig_search_lt"]
            scan_count_origin = task["orig_scan_count"]
            event_count_origin = task["orig_event_count"]
            result_count_origin = task["orig_result_count"]
            savedsearch_key = app+"/"+savedsearch_name
            
            logger_file.info("006","Process this task: {0}".format(str(task)))

            if savedsearch_key not in savedsearches:
                # Try to connect to the Splunk API
                logger_file.debug("007","Connecting to Splunk API with the app context set to {app}...".format(app=app))
                try:
                    spl = client.connect(app=app, owner=owner, token=spl_token)
                    logger_file.debug("008","Connected to Splunk API successfully")
                except Exception as e:
                    logger_file.error("009","{}".format(e.msg))

                # Get the context of the savedsearch            
                try:
                    savedsearches[savedsearch_key] = spl.saved_searches[savedsearch_name]
                    logger_file.debug("010","Savedsearch '"+app+"/"+savedsearch_name+"' successfully recovered and cached.")
                except Exception as e:
                    logger_file.error("011","The savedsearch '"+app+"/"+savedsearch_name+"' can't be found. Check if there is any misconfiguration (app, savedsearch name or permissions (minimum shared within the app)")
                
            else:
                logger_file.debug("014","Savedsearch '"+app+"/"+savedsearch_name+"' is already retrieved from the previous event, continue with the same data...")
        
            # Get the savedsearch
            savedsearch = savedsearches[savedsearch_key]

            # Get the search content
            savedsearch_search = savedsearch["search"]

            # Add a "search" command if needed
            if savedsearch_search[0] != "|" and not savedsearch_search.startswith("search"):
                logger_file.debug("015","Adding a 'search' command at the beginning as we are searching on an index/sourcetype (query is starting with {query_substr}...)".format(query_substr=savedsearch_search[0:15]))
                savedsearch_search = "search "+savedsearch_search

            dispatch_params = None
            job = None

            dispatch_params = {"dispatch.ttl": configuration.additional_parameters["dispatch_ttl"], "dispatch.earliest_time": dispatch_earliest, "dispatch.latest_time": dispatch_latest, "force_dispatch": True, "trigger_actions": False}

            try:
                job = savedsearch.dispatch(**dispatch_params)
            except Exception as e:
                logger_file.error("021","The savedsearch '"+app+"/"+savedsearch["name"]+"' can't be dispatched. Make sure your savedsearch is enabled or check in the splunkd.log for more information")
                sys.exit(40)

            logger_file.info("040","Healthcheck job '{uid}' for original SID {sid_origin} for the savedsearch '{app}/{savedsearch}' was dispatched. SID of the healthcheck job is '{job_sid}'. First job was run at '{time}' ({time_readable}) with an original scan count was '{scan_count}', event count was '{event_count}' and result count was '{result_count}'".format(uid=hc_uid,sid_origin=sid_origin,app=app,savedsearch=savedsearch_name,job_sid=job.sid,time=timestamp_origin,time_readable=timestamp_origin_readeable,scan_count=scan_count_origin,event_count=event_count_origin,result_count=result_count_origin))

            # Log all the information in order to retrieve the results in a dedicated dashboard

            event_message = {
                "type": "healthcheck:job_dispatched",
                "uid": hc_uid,
                "created_time": hc_created_time,
                "created_author": hc_created_author,
                "jobs": {
                    "origin": {
                        "sid": sid_origin,
                        "timestamp": timestamp_origin,
                        "timestamp_readable": timestamp_origin_readeable,
                        "scan_count": scan_count_origin,
                        "event_count": event_count_origin,
                        "result_count": result_count_origin
                    },
                    "healthcheck": {
                        "sid": str(job.sid).replace("'","")
                    }
                },
                "app": app,
                "savedsearch_name": savedsearch_name,
            }

            # Add event to be indexed
            logger_file.debug("045","Creating a 'healthcheck:job_dispatched' event to be indexed...")
            helper.addevent(raw=json.dumps(event_message), sourcetype="detection_backfill:events")
        
        # Index events
        logger_file.debug("050","Write all 'healthcheck:job_dispatched' events to be indexed...")
        helper.writeevents(index=configuration.additional_parameters["index_results"], host=helper.settings["server_host"], source="app:detection_backfill")

    return 0
