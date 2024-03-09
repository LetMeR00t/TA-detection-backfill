
# encoding = utf-8

# Author: Alexandre Demeyer <letmer00t@gmail.com>

import globals
import sys
import datetime
import tzlocal
import splunklib.client as client
from common import Settings, LoggerFile

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
    token = helper.settings["sessionKey"] if "sessionKey" in helper.settings else helper.settings["session_key"]
    sid = helper.settings["sid"]
    globals.log_context = "[sid={0}]".format(sid)

    # Default app is the current one
    app = "TA-detection-backfill"

    # Try to connect to the Splunk API for the Detection Backfill app
    logger_file.debug("001","Connecting to Splunk API with the app context set to {app}...".format(app=app))
    try:
        spl_detection_backfill = client.connect(app=app, owner=owner, token=token)
        logger_file.debug("002","Connected to Splunk API successfully")
    except Exception as e:
        logger_file.error("003","{}".format(e.msg))

    # Get settings
    configuration = Settings(spl_detection_backfill, helper.settings, logger)

    # Get the information from the events and process them
    events = helper.get_events()

    current_app = None
    current_savedsearch = None
    spl = None
    savedsearch = None

    savedsearches = {}

    # Process each event
    for event in events:

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
                logger_file.error("015","A required field wasn't found in the event: '{field}'. Expected fields are: {expected_fields}".format(field=p,expected_fields=expected_fields))
                sys.exit(5)

        ## Get the savedsearch and dispatch again the search
        sid_origin = event["search_id"]
        timestamp_origin = int(event["exec_time"])
        timestamp_origin_readeable = datetime.datetime.fromtimestamp(timestamp_origin,tz=tzlocal.get_localzone()).strftime("%c %z")
        scan_count_origin = event["scan_count"]
        event_count_origin = event["event_count"]
        result_count_origin = event["result_count"]
        dispatch_earliest = event["search_et"]
        dispatch_latest = event["search_lt"]
        app = event["app"]
        savedsearch_name = event["savedsearch_name"]
        savedsearch_key = app+"/"+savedsearch_name

        logger_file.info("006","Process this event: {0}".format(str(event)))

        if savedsearch_key not in savedsearches:
            # Try to connect to the Splunk API
            logger_file.debug("007","Connecting to Splunk API with the app context set to {app}...".format(app=app))
            try:
                spl = client.connect(app=app, owner=owner, token=token)
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

        dispatch_params = {"now": timestamp_origin, "earliest_time": dispatch_earliest, "latest_time": dispatch_latest}

        # Dispatch the search
        # Log all the information in order to retrieve the results in a dedicated dashboard
        try:
            job = spl.jobs.create(query=savedsearch_search, **dispatch_params)
        except Exception as e:
            logger_file.error("025","The savedsearch '"+app+"/"+savedsearch["name"]+"' can't be dispatched. Make sure your savedsearch is enabled or check in the splunkd.log for more information. {e}".format(e=e))

        logger_file.info("040","Healthcheck job for sid_origin {sid_origin} for the savedsearch '{app}/{savedsearch}' was dispatched. SID of the healthcheck job is '{job_sid}'. First job was run at '{time}' ({time_readable}) with an original scan count was '{scan_count}', event count was '{event_count}' and result count was '{result_count}'".format(sid_origin=sid_origin,app=app,savedsearch=savedsearch_name,job_sid=job.sid,time=timestamp_origin,time_readable=timestamp_origin_readeable,scan_count=scan_count_origin,event_count=event_count_origin,result_count=result_count_origin))


    return 0
