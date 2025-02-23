
# encoding = utf-8

# Author: Alexandre Demeyer <letmer00t@gmail.com>

import uuid
import globals
import json
import hashlib
import splunklib.client as client
import splunklib.results as results
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
    logger_file = LoggerFile(logger, "CAA-IRFS")
    helper.log_info("[CAA-IRFS-000] LOG level to: " + helper.log_level)
    helper.set_log_level(helper.log_level)

    # Build the context around the Splunk instance
    spl = None
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
        logger_file.debug("002","Successful connection to Splunk API")
    except Exception as e:
        logger_file.error("003","{}".format(e.msg))

    # Get settings
    configuration = Settings(spl_detection_backfill, helper.settings, logger)

    # Get the information from the events and process them
    events = helper.get_events()

    # Try to connect to the Splunk API
    logger_file.debug("007","Connecting to Splunk API with the app context set to {app}...".format(app=app))
    try:
        spl = client.connect(app=app, owner=owner, token=token)
        logger_file.debug("008","Successful connection to Splunk API")
    except Exception as e:
        logger_file.error("009","{}".format(e.msg))

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

        # Get search ID
        if "search_id" in event:
            
            # Get the SID
            sid = event["search_id"].replace("'","")

            logger_file.debug("020","Try to get the job from the SID '{sid}'...".format(sid=sid))

            # Get the job results
            job = spl.job(sid=sid)

            # Parse the results
            rr = results.JSONResultsReader(job.results(output_mode='json'))
            logger_file.debug("021","Results from the job SID '{sid}' retrieved".format(sid=sid))

            # Process each result
            logger_file.debug("030","Process events to be indexed...")
            for result in rr:
                if isinstance(result, results.Message):
                    # Diagnostic messages may be returned in the results
                    logger_file.warn("050",'%s: %s' % (result.type, result.message))
                elif isinstance(result, dict):
                    # Normal events are returned as dicts
                    result_uuid = str(uuid.uuid4())
                    result_formatted = {
                        "uid": result_uuid,
                        "type": "result",
                        "healthcheck_uid": event["healthcheck_uid"],
                        "job": {
                            "sid": sid
                        },
                        "result_hash": hashlib.sha256(str(result).encode('utf-8')).hexdigest(),
                        "result": result
                    }
                    # Add for indexation
                    helper.addevent(raw=json.dumps(result_formatted), sourcetype="detection_backfill:healthcheck:result")
                else:
                    logger_file.error("60","An expected behavior occured during processing of: %s" % result)

        else:
            logger_file.debug("060","No 'search_id' field found in the event: " + str(event)+", skipped...")

    # Once all events were processed, index all the results
    index_results = configuration.additional_parameters["index_results"]
    logger_file.debug("070",f"Write all 'result' events to the index {index_results}...")
    helper.writeevents(index=index_results, host=helper.settings["server_host"], source="app:detection_backfill")

    return 0
