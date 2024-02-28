# encoding = utf-8

# Author: Alexandre Demeyer <letmer00t@gmail.com>
# Inspired by: Donald Murchison

import splunk.Intersplunk
import re
import sys
import globals
from common import Settings, LoggerFile, RelativeTime
from ta_logging import setup_logging
import splunklib.client as client
import datetime
import tzlocal
from crontab import CronTab

if __name__ == '__main__':
    
    globals.initialize_globals()

    # First, parse the arguments
    # Get the keywords and options passed to this command
    keywords, options = splunk.Intersplunk.getKeywordsAndOptions()

    # Get the previous search results
    results,dummyresults,settings = splunk.Intersplunk.getOrganizedResults()

    # Prepare the output results
    outputResults = []

    # Get logger
    logger = setup_logging("detection_backfill_evaluate_savedsearches_to_rerun")
    logger_file = LoggerFile(logger, "CC-ESTR")

    # Try to connect to the Splunk API
    logger_file.info("005","Connecting to Splunk API...")
    try:
        spl = client.connect(token=settings["sessionKey"])
        logger_file.info("006","Connected to Splunk API successfully")
    except Exception as e:
        logger_file.error("007","{}".format(e.msg))

    # Get settings
    configuration = Settings(spl, settings, logger)
    now = datetime.datetime.now()

    # Process each result
    for result in results:
        
        # Extract useful information
        outage_period_earliest = RelativeTime(pattern=result["outage_period_earliest"], time=now.timestamp(), logger=logger).datetime_calculated.timestamp()
        outage_period_latest = RelativeTime(pattern=result["outage_period_latest"], time=now.timestamp(), logger=logger).datetime_calculated.timestamp()
        savedsearches_regex = result["savedsearches_regex"]

        logger_file.info("008","'{0}' ran the script with the following inputs: outage_period_earliest='{1}', outage_period_latest='{2}', savedsearches_regex='{3}'".format(settings["owner"],outage_period_earliest,outage_period_latest,savedsearches_regex))
        
        # Compile the regex
        filter_savedsearches_regex = re.compile(savedsearches_regex)
        filter_timestamp = re.compile("^\d+(?:\.\d*)?$")

        # Find all savedsearches
        logger_file.info("010","Start to analyze all savedsearches")
        apps = {}
        savedsearches = []
        for search in spl.saved_searches:
            logger_file.debug("011","Run regexp '{0}' on '{1}/{2}'".format(savedsearches_regex, search.access["app"], search.name))
            # Does not rerun disabled searches
            if filter_savedsearches_regex.search(search.name) and search.is_scheduled=="1" and search.disabled=="0":
                logger_file.info("015","Regexp '{0}' is matching '{1}/{2}'".format(savedsearches_regex, search.access["app"], search.name))
                if search.access["app"] in apps:
                    apps[search.access["app"]] += 1
                else:
                    apps[search.access["app"]] = 1
                savedsearches.append(search)
            elif filter_savedsearches_regex.search(search.name):
                # Match but ignored as not scheduled or disabled
                logger_file.info("016","Regexp '{0}' is matching '{1}/{2}' BUT this was ignored as it's either not scheduled or disabled.".format(savedsearches_regex, search.access["app"], search.name))
        logger_file.info("019","End of all savedsearches analysis, results found ("+str(len(savedsearches))+") by app: "+str(apps))

        # Process each savedsearch identified on the outage period
        for savedsearch in savedsearches:
            logger_file.debug("020","Processing savedsearch '{0}/{1}'...".format(savedsearch.access["app"],savedsearch.name))
            
            # Initialize savedsearch context
            backfill_output = {"app": savedsearch.access["app"], "savedsearch": savedsearch.name, "et": savedsearch['content']['dispatch.earliest_time'], "lt": savedsearch['content']['dispatch.latest_time'], "cron": savedsearch['content']['cron_schedule']}

            # Initialize other variables
            backfill_output["dispatch_time"] = ""
            backfill_output["comment"] = ""

            # Get earliest and latest pattern for savedsearch
            ss_dispatch_earliest = savedsearch['content']['dispatch.earliest_time']
            ss_dispatch_latest = savedsearch['content']['dispatch.latest_time']
            ss_cron = CronTab(savedsearch['content']['cron_schedule'])

            logger_file.debug("021","Got dispatch_earliest='{0}', dispatch_latest='{1}, cron_schedule='{2}'".format(ss_dispatch_earliest,ss_dispatch_latest,savedsearch['content']['cron_schedule']))
        
            # Phase 1: Identify earliest outage time to first latest time period
            outage_period_earliest_f = float(outage_period_earliest)
            outage_period_latest_f = float(outage_period_latest)
            next_schedule_f = outage_period_earliest_f + ss_cron.next(now=datetime.datetime.fromtimestamp(outage_period_earliest_f,tzlocal.get_localzone()),default_utc=False)
            
            next_dispatch_earliest_f = next_schedule_f
            if ss_dispatch_earliest == "0" and ss_dispatch_latest is None:
                    backfill_output["dispatch_time"] = -1
                    logger_file.warn("023","Savedsearch '{0}' is looking on 'All time'. To avoid performance issues, this savedsearch will be skipped.".format(savedsearch.name))   
            elif filter_timestamp.search(ss_dispatch_earliest) and filter_timestamp.search(ss_dispatch_latest):
                # Run the savedsearch as is only once if it's in the range of outage
                if (float(ss_dispatch_latest) > outage_period_earliest_f and outage_period_latest_f > float(ss_dispatch_latest)) or (float(ss_dispatch_earliest) > outage_period_earliest_f and outage_period_latest_f > float(ss_dispatch_earliest)) or (float(ss_dispatch_earliest) > outage_period_earliest_f and outage_period_latest_f > float(ss_dispatch_latest)):
                    backfill_output["comment"] = ["Phase 1: Evaluate first outage range","Time: Next dispatch time calculated from the cron, #0 (static savedsearch, so only once)"]
                    backfill_output["dispatch_time"] = next_schedule_f
                else:
                    backfill_output["dispatch_time"] = -1
                    logger_file.warn("024","Static times from the savedsearch '{0}' aren't contained in the outage period '{1}->{2}', this savedsearch will be skipped.".format(savedsearch.name,str(outage_period_earliest_f),str(outage_period_latest_f)))
            elif filter_timestamp.search(ss_dispatch_earliest):
                # Earliest is a static timestamp
                ss_dispatch_earliest_f = float(ss_dispatch_earliest)
                if datetime.datetime.fromtimestamp(ss_dispatch_earliest_f,tzlocal.get_localzone()) > datetime.datetime.fromtimestamp(outage_period_latest_f,tzlocal.get_localzone()):
                    # Case 1: static timestamp is earlier than the end of the outage, we skip it
                    backfill_output["dispatch_time"] = -1
                    logger_file.warn("025","Static earliest time from the savedsearch '{0}' is later than the end of the outage '{1}', this range will be skipped.".format(str(ss_dispatch_earliest),str(outage_period_latest_f)))
                else:
                    # Case 2: static timestamp is later than or equals to the end of the outage, we take it
                    backfill_output["dispatch_time"] = next_schedule_f
                    backfill_output["comment"] = ["Phase 1: Evaluate first outage range","Time: Static earliest time is earlier than next schedule, keep next schedule time"]
            elif filter_timestamp.search(ss_dispatch_latest):
                # Latest is a static timestamp
                backfill_output["dispatch_time"] = -1
                logger_file.warn("026","Savedsearch '{0}' has static timestamp as latest but not on earliest. This savedsearch will be skipped as not supported by the script.".format(savedsearch.name))
            else:
                backfill_output["comment"] = ["Phase 1: Evaluate first outage range","Time: Next dispatch time calculated from the cron, #0"]
                backfill_output["dispatch_time"] = next_schedule_f

            if backfill_output["dispatch_time"] != -1:
                # No issue found during the processing, we can consider this
                outputResults.append(backfill_output.copy())

                # Phase 2: Identify all outage times from earliest/latest executions of the savedsearch
                if filter_timestamp.search(ss_dispatch_earliest) and filter_timestamp.search(ss_dispatch_latest):
                    # Nothing to do as managed during Phase 1
                    pass
                elif filter_timestamp.search(ss_dispatch_latest):
                    # Latest is a static timestamp
                    # Nothing to do as already skipped during Phase 1
                    pass
                else:
                    # We consider latest as being a relative time pattern
                    counter = 0
                    logger_file.debug("050","Starting Phase 2 from this next schedule date: {0} ({1}) to outage period latest time {2} ({3})".format(next_schedule_f,datetime.datetime.fromtimestamp(next_schedule_f,tzlocal.get_localzone()).strftime("%c %z"),outage_period_latest_f,datetime.datetime.fromtimestamp(outage_period_latest_f,tzlocal.get_localzone()).strftime("%c %z")))
                    while (outage_period_latest_f > next_schedule_f and counter < 100000):
                        # Looping to have all the possibilities as soon as we aren't exceeding the outage period latest time
                        # Safe counter: After 100,000 attempts, we end the script to ensure it has an end. More than 100,000 attempts must be processed into divided outage period of time.
                        counter += 1
                        next_schedule_f = next_schedule_f + ss_cron.next(now=datetime.datetime.fromtimestamp(next_schedule_f,tzlocal.get_localzone()),default_utc=False)
                        logger_file.debug("055","Next calculated schedule: {0} ({1})".format(next_schedule_f,datetime.datetime.fromtimestamp(next_schedule_f,tzlocal.get_localzone()).strftime("%c %z")))
                        backfill_output["dispatch_time"] = next_schedule_f
                        backfill_output["comment"] = ["Phase 2: Evaluate inter ranges","Time: Next dispatch time calculated from the cron, #"+str(counter)]
                        if outage_period_latest_f > next_schedule_f:
                        # No issue found during the processing, we can consider this
                            outputResults.append(backfill_output.copy())
                    if counter >= 100000:
                        logger_file.error("070","More than 100,000 attemps were made, which is representing too much for this savedsearch and the given outage period. More than 100,000 attempts must be processed into divided outage period of time, exiting ...")
                        sys.exit(60)
                        
                # Phase 3: Identify the last earliest time to the latest outage time
                if filter_timestamp.search(ss_dispatch_earliest) and filter_timestamp.search(ss_dispatch_latest):
                    # Nothing to do as managed during Phase 1
                    pass
                elif filter_timestamp.search(ss_dispatch_latest):
                    # Latest is a static timestamp
                    # Nothing to do as already skipped during Phase 1
                    pass
                else:
                    # We consider latest as being a relative time pattern
                    backfill_output["dispatch_time"] = next_schedule_f
                    backfill_output["comment"] = ["Phase 3: Evaluate last outage range","Time: Next dispatch time calculated from the cron, #"+str(counter+1)]
                    outputResults.append(backfill_output.copy())
            else:
                # Something isn't right with the search, skip it and keep processing for the others
                pass

            logger_file.debug("080","End of processing savedsearch '{0}/{1}'.".format(savedsearch.access["app"],savedsearch.name))


    splunk.Intersplunk.outputResults(outputResults)
