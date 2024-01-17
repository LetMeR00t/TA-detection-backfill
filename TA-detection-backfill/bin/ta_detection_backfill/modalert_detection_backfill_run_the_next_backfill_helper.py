
# encoding = utf-8

# Author: Alexandre Demeyer <letmer00t@gmail.com>
# Inspired by: Donald Murchison

import globals
import sys
import datetime
import tzlocal
import splunklib.client as client
from common import LoggerFile, Backlog, RelativeTime

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
    trigger = helper.get_param("trigger")
    helper.log_info("trigger={}".format(trigger))


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
    logger_file = LoggerFile(logger, "CAA-RTNB")
    helper.log_info("[CAA-RTNB-001] LOG level to: " + helper.log_level)
    helper.set_log_level(helper.log_level)

    # Build the context around the Splunk instance
    owner = helper.settings["owner"]
    token = helper.settings["session_key"]
    sid = helper.settings["sid"]
    globals.log_context = "[sid={0}]".format(sid)

    # Get parameters
    trigger = helper.get_param("trigger")

    # Get backlog
    spl_token = helper.settings["sessionKey"] if "sessionKey" in helper.settings else helper.settings["session_key"]
    backlog = Backlog(spl_token=spl_token,logger=logger)

    # Get the information from the events and process them
    events = helper.get_events()
    counter = 0
    for event in events:
        counter += 1

    logger_file.info("002","Counter set to {0}. Will process the first {0} elements of the backlog...".format(str(counter)))

    # Get next task
    tasks = backlog.next_tasks(counter)

    if tasks == []:
        logger_file.info("003","Backlog is empty, nothing to rerun.")

    for task in tasks:
        
        logger_file.info("004","Process this task: {0}, with trigger set to: {1}".format(str(task),trigger))

        dispatch_time = float(task["dispatch_time"])
        app = task["app"]
        savedsearch_name = task["savedsearch"]

        # Try to connect to the Splunk API
        logger_file.debug("005","Connecting to Splunk API...")
        try:
            spl = client.connect(app=app, owner=owner, token=token)
            logger_file.debug("006","Connected to Splunk API successfully")
        except Exception as e:
            logger_file.error("007","{}".format(e.msg))

        # Get the context of the savedsearch
        try:
            savedsearch = spl.saved_searches[savedsearch_name]
            logger_file.debug("010","Savedsearch '"+app+"/"+savedsearch_name+"' successfully recovered")
        except Exception as e:
            logger_file.error("011","The savedsearch '"+app+"/"+savedsearch_name+"' can't be found. Check if there is any misconfiguration (app, savedsearch name or permissions (minimum shared within the app))")
            sys.exit(11)

        dispatch_time_readable = datetime.datetime.fromtimestamp(dispatch_time,tz=tzlocal.get_localzone()).strftime("%c %z")

        logger_file.info("020","Job for the savedsearch '"+app+"/"+savedsearch_name+"' will be dispatched with a reference time set to "+dispatch_time_readable+" ("+str(dispatch_time)+")...")

        # Get earliest dispatch time
        earliest_time = RelativeTime(savedsearch['content']['dispatch.earliest_time'],dispatch_time,logger=logger).datetime_calculated.timestamp()

        # Get latest dispatch time
        latest_time = RelativeTime(savedsearch['content']['dispatch.latest_time'],dispatch_time,logger=logger).datetime_calculated.timestamp()

        # Prepare parameters
        dispatch_kwargs = {"dispatch.earliest_time": str(earliest_time), "dispatch.latest_time": str(latest_time), "force_dispatch": True}

        # Check if triggers need to be activated
        if trigger == "1":
            dispatch_kwargs["trigger_actions"] = True
        else:
            dispatch_kwargs["trigger_actions"] = False

        logger_file.debug("030","Savedsearch dispatch parameters: "+str(dispatch_kwargs))

        # Finally, let's rerun this savedsearch on the right time
        try:
            job = savedsearch.dispatch(**dispatch_kwargs)
        except Exception as e:
            logger_file.error("040","The savedsearch '"+app+"/"+savedsearch_name+"' can't be dispatched. Make sure your savedsearch is enabled or check in the splunkd.log for more information")
            sys.exit(40)

        logger_file.info("050","Job for the savedsearch '"+app+"/"+savedsearch_name+"' dispatched as if the current time was "+dispatch_time_readable+" ("+str(dispatch_time)+") was created. Job SID '"+job.sid+"' dispatched from backfill uid '"+task["bf_uid"]+"', batch '"+task["bf_batch_name"].replace("'","\"")+"' ("+task["bf_batch_id"]+")")

        # Logout from Splunk
        spl.logout()


    return 0
