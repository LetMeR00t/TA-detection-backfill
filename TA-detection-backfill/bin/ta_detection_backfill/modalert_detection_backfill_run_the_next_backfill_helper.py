
# encoding = utf-8

# Author: Alexandre Demeyer <letmer00t@gmail.com>
# Inspired by: Donald Murchison

import globals
import sys
import datetime
import tzlocal
import hashlib
import splunklib.client as client
from common import Settings, LoggerFile, Backlog, RelativeTime, SPLCodeInjection

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
    logger_file = LoggerFile(logger, "CAA-RTNB")
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

    # Get backlog
    backlog = Backlog(spl_token=token,logger=logger)

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

    for task in tasks:

        dispatch_time = float(task["dispatch_time"])
        app = task["app"]
        savedsearch_name = task["savedsearch"]
        spl_code_injection_id = task["bf_spl_code_injection_id"]
        trigger = True if "trigger" in task and task["trigger"] == "1" else False 

        logger_file.info("006","Process this task: {0}, with trigger set to: {1}".format(str(task),trigger))

        # Try to connect to the Splunk API
        logger_file.debug("007","Connecting to Splunk API with the app context set to {app}...".format(app=app))
        try:
            spl = client.connect(app=app, owner=owner, token=token)
            logger_file.debug("008","Connected to Splunk API successfully")
        except Exception as e:
            logger_file.error("009","{}".format(e.msg))

        # Get the context of the savedsearch            
        try:
            savedsearch = spl.saved_searches[savedsearch_name]
            logger_file.debug("010","Savedsearch '"+app+"/"+savedsearch_name+"' successfully recovered")
        except Exception as e:
            logger_file.error("011","The savedsearch '"+app+"/"+savedsearch_name+"' can't be found. Check if there is any misconfiguration (app, savedsearch name or permissions (minimum shared within the app))")
            sys.exit(11)

        # Check if there is a SPL code injection
        ## If no SPL code injection is requested
        if spl_code_injection_id != "0":
            spl_code_injections = SPLCodeInjection(spl_token=token,logger=logger).get()
            if spl_code_injection_id in spl_code_injections:
                spl_injection_code_content = spl_code_injections[spl_code_injection_id]
            else:
                logger_file.error("014","Macro ID '{macro_id}' was not found in the SPL code injections lookup, please check where is the issue (backlog or SPL code injection lookup)".format(macro_id=spl_code_injection_id))
                sys.exit(14)
            logger_file.info("015","SPL code injection request detected: ({id}) '{name}'".format(id=spl_injection_code_content["id"],name=spl_injection_code_content["name"]))

            # Consider the new app as the Detection Backfill one
            app = "TA-detection-backfill"

            # Create the new savedsearch 
            new_savedsearch_name = savedsearch["name"]+" (spl-code-injection-{id})".format(id=spl_injection_code_content["id"])
            savedsearch_properties = savedsearch.content
            # Keep only necessary fields
            valid_keys = ["description", "search",  "alert_type", "cron_schedule", "dispatch.earliest_time", "dispatch.latest_time", "dispatch.index_earliest", "dispatch.index_latest",  "alert.digest_mode", "alert.expires", "alert.managedBy", "alert.severity", "alert.suppress", "alert.suppress.fields", "alert.suppress.group_name", "alert.suppress.period", "alert.track", "alert_comparator", "alert_condition", "alert_threshold", "alert_type", "allow_skew", "is_scheduled", "is_visible", "max_concurrent", "realtime_schedule", "restart_on_searchpeer_add", "run_n_times", "run_on_startup", "schedule_as", "schedule_priority", "schedule_window"]
            savedsearch_properties = {p:v for p, v in savedsearch_properties.items() if (p in valid_keys or p.startswith("action")) and (v is not None and v != "")}

            # Inject the new code
            macro_position = int(spl_injection_code_content["position"])
            macro_content = spl_injection_code_content["macro"]
            savedsearch_split = savedsearch_properties["search"].split("|")

            # Depending on the first line of the search, review the macro position
            if savedsearch_properties["search"][0] == "|":
                # This means that the first character of the search is a pipe so review the macro position to match the good one
                macro_position += 1
            
            if macro_position == 0:
                # Append at the beginning of the search
                savedsearch_properties["search"] = "| `{macro}`\n".format(macro=macro_content)+savedsearch_properties["search"]
            elif macro_position == -1 or len(savedsearch_split) <= macro_position:
                # Append at the end of the search
                savedsearch_properties["search"] += "\n| `{macro}`".format(macro=macro_content)
            elif macro_position > 0:
                # Add at the given position
                savedsearch_split.insert(macro_position, " `{macro}`\n".format(macro=macro_content))
                savedsearch_properties["search"] = "|".join(savedsearch_split)

            ## Check if the savedsearch exists and if we need to recreate it
            if new_savedsearch_name in spl.saved_searches:
                savedsearch_existing = spl.saved_searches[new_savedsearch_name]
                # Check the signatures to evaluate what we need to do
                signature_new = str(savedsearch_properties["search"]+str(savedsearch["dispatch.earliest_time"])+str(savedsearch["dispatch.latest_time"])+str(savedsearch["dispatch.index_earliest"])+str(savedsearch["dispatch.index_latest"])).encode('utf-8')
                signature_existing = str(savedsearch_existing["search"]+str(savedsearch_existing["dispatch.earliest_time"])+str(savedsearch_existing["dispatch.latest_time"])+str(savedsearch_existing["dispatch.index_earliest"])+str(savedsearch_existing["dispatch.index_latest"])).encode('utf-8')

                if hashlib.sha256(signature_new).hexdigest() != hashlib.sha256(signature_existing).hexdigest():
                    logger_file.debug("017","Code injection done, new search is '{search}'".format(search=savedsearch_properties["search"]))
                    # It means that something changed, so we recreate it
                    logger_file.debug("019","Recreating new active but non-scheduled savedsearch: '{name}'".format(name=new_savedsearch_name))
                    if new_savedsearch_name in spl_detection_backfill.saved_searches:
                        # This means that the search already exists, so delete it
                        logger_file.debug("020","Deleting existing savedsearch first: '{name}'...".format(name=new_savedsearch_name))
                        spl_detection_backfill.saved_searches.delete(new_savedsearch_name)

                    # Create the savedsearch and make it the one to use
                    savedsearch = spl_detection_backfill.saved_searches.create(name=new_savedsearch_name, **savedsearch_properties)

                else:
                    # It means that nothing changed and we can reuse the existing one
                    logger_file.debug("021","Get existing (and not modified) non-scheduled savedsearch: '{name}'".format(name=new_savedsearch_name))
                    savedsearch = spl.saved_searches[new_savedsearch_name]
            else:
                logger_file.debug("022","Creating new active but non-scheduled savedsearch: '{name}'".format(name=new_savedsearch_name))
                # Create it as it doesn't exist yet
                savedsearch = spl_detection_backfill.saved_searches.create(name=new_savedsearch_name, **savedsearch_properties)

        else:
            logger_file.debug("024","No SPL code injection request detected, continue with original savedsearch.")           

        dispatch_time_readable = datetime.datetime.fromtimestamp(dispatch_time,tz=tzlocal.get_localzone()).strftime("%c %z")

        logger_file.info("025","Job for the savedsearch '"+app+"/"+savedsearch["name"]+"' will be dispatched with a reference time set to "+dispatch_time_readable+" ("+str(dispatch_time)+")...")

        # Get earliest dispatch time
        earliest_time = RelativeTime(savedsearch['content']['dispatch.earliest_time'],dispatch_time,logger=logger).datetime_calculated.timestamp()

        # Get latest dispatch time
        latest_time = RelativeTime(savedsearch['content']['dispatch.latest_time'],dispatch_time,logger=logger).datetime_calculated.timestamp()

        # Prepare parameters, including the trigger
        dispatch_kwargs = {"dispatch.ttl": configuration.additional_parameters["dispatch_ttl"], "dispatch.earliest_time": str(earliest_time), "dispatch.latest_time": str(latest_time), "force_dispatch": True, "trigger_actions": trigger}

        logger_file.debug("030","Savedsearch dispatch parameters: "+str(dispatch_kwargs))

        # If we recreated a savedsearch, enable/disable it just for this execution
        if app == "TA-detection-backfill":
            logger_file.debug("039","Enabling the savedsearch '"+app+"/"+savedsearch["name"]+"'...")
            savedsearch.enable()

        # Finally, let's rerun this savedsearch on the right time
        try:
            job = savedsearch.dispatch(**dispatch_kwargs)
        except Exception as e:
            logger_file.error("040","The savedsearch '"+app+"/"+savedsearch["name"]+"' can't be dispatched. Make sure your savedsearch is enabled or check in the splunkd.log for more information")
            sys.exit(40)

        logger_file.info("050","Job for the savedsearch '"+app+"/"+savedsearch["name"]+"' dispatched was created as if the current time was "+dispatch_time_readable+" ("+str(dispatch_time)+"). Job SID '"+job.sid+"' dispatched from backfill uid '"+task["bf_uid"]+"', batch '"+task["bf_batch_name"].replace("'","\"")+"' ("+task["bf_batch_id"]+")")

        # If we recreated a savedsearch, enable/disable it just for this execution
        if app == "TA-detection-backfill":
            logger_file.debug("051","Disabling the savedsearch '"+app+"/"+savedsearch["name"]+"'...")
            savedsearch.disable()

        # Logout from Splunk
        spl.logout()


    return 0
