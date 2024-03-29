import ta_detection_backfill_declare
import globals
import re
import os
import sys
import datetime
import csv
from dateutil.relativedelta import relativedelta
import tzlocal
import splunklib.client as client
import logging
import json
import random

# Author: Alexandre Demeyer <letmer00t@gmail.com>
# Inspired by: Donald Murchison

class LoggerFile(object):

    def __init__(self, logger = None, command_id = ""):
        self.logger = logger
        self.command_id = str(command_id)

    def _log(self, type = "info", id = "?", message = ""):
        if globals.log_context == "[]":
            log_context = ""
        else:
            log_context = globals.log_context
        if type == "debug" and self.logger.getEffectiveLevel() != logging.DEBUG:
            pass
        else:
            getattr(self.logger, type)(log_context+"["+globals.next_log_id()+"]["+self.command_id+"-"+str(id)+"] "+str(message))

    def info(self, id = "?", message = ""):
            self._log("info", id=id, message=message)

    def warn(self, id = "?", message = ""):
            self._log("warn", id=str(id)+"-WARNING", message=message)

    def error(self, id = "?", message = ""):
            self._log("error", id=str(id)+"-ERROR", message=message)

    def debug(self, id = "?", message = ""):
            self._log("debug", id=id, message=message)

class Pattern(object):
    
    def __init__(self, original_pattern:str, logger = None):
        """This function is used to process and extract information from a pattern into a dedicated structure

        Args:
            original_pattern (str): A pattern to be process
            snap (str, optional): The snap from the pattern. Defaults to None.
            snapOff (str, optional): The snap offset from the pattern. Defaults to None.
            snapUnit (str, optional): The snap unit from the pattern. Defaults to None.
            offset1 (str, optional): The offset 1 from the pattern. Defaults to None.
            unit1 (str, optional): The unit 1 from the pattern. Defaults to None.
            offset2 (str, optional): The offset 2 from the pattern. Defaults to None.
            unit2 (str, optional): The unit 2 from the pattern. Defaults to None.
        """

        self.original_pattern = original_pattern
        self.logger = logger
        self.logger_file = LoggerFile(logger, "P")
        # Initialize values to None
        self.snap = None
        self.snapOff = None
        self.snapUnit = None
        self.offset1 = None
        self.unit1 = None
        self.offset2 = None
        self.unit2 = None
        self._process_pattern()
        
    def _process_pattern(self):
        """This is used to process a given pattern
        """
        m = re.match("((?P<offset1>[+-]?\d+)(?P<unit1>[a-zA-Z]+)(?:(?P<offset2>[+-]\d+)(?P<unit2>[a-zA-Z]+))?)?(?:@(?P<snap>[a-zA-Z]+)(?:(?P<snapOff>[+-]\d+)(?P<snapUnit>[a-zA-Z]+))?)?",self.original_pattern)

        self.logger_file.debug("004","Relative time - Processing pattern '{0}'...".format(self.original_pattern))

        if m and self.original_pattern != "now":

            # Extract the information
            self.snap = m.group('snap')
            self.snapOff = m.group('snapOff')
            self.snapUnit = m.group('snapUnit')
            self.offset1 = m.group('offset1')
            self.unit1 = m.group('unit1')
            self.offset2 = m.group('offset2')
            self.unit2 = m.group('unit2')
        
            self.logger_file.debug("005","Relative time - Pattern extracted: snap='{0}', snapOff='{1}', snapUnit='{2}', offset1='{3}', unit1='{4}', offset2='{5}', unit1='{6}'".format(self.snap,self.snapOff,self.snapUnit,self.offset1,self.unit1,self.offset2,self.unit2))

        else:
            self.logger_file.debug("006","Relative time - None pattern extracted, either wrong pattern format or value set to 'now'")


class RelativeTime(object):

    def __init__(self, pattern:str, time:float, logger):
        """This function is used to initialize a RelativeTime object

        Args:
            pattern (str): Pattern to be used to calculate the relative time from the original time
            time (float): Original time on which we want to apply the pattern
            logger (Logger): A logger to use. Defaults to None.
        """

        # Initialize all settings
        self.logger = logger
        self.logger_file = LoggerFile(logger, "RT")
        self.tz = tzlocal.get_localzone()
        self.pattern = Pattern(original_pattern=pattern, logger=logger)
        self.time_original = time
        self.time_calculated = time
        self.datetime_calculated = None
        self._calculate_target_time()

    def _apply_snap(self, unit:str):
        """This function allows you to apply a Splunk snap to a given time
        Inherited and refactored from the Splunk Rerun app

        Args:
            unit (str): Unit to process as a snap

        Raises:
            Exception: A generic error in case we can't parse the snap
        """
        
        # Get runtime as Datetime based on timezone
        datetime_time = datetime.datetime.fromtimestamp(int(self.time_calculated),tz=self.tz)
        if (unit == None):
            x = self.time_calculated
        elif (unit == "m" or "min" in unit):
            x = datetime_time.replace(second=0).timestamp()
        elif (unit == "h" or "hr" in unit or "hour" in unit):
            x = datetime_time.replace(minute=0,second=0).timestamp()
        elif (unit == "d" or  "day" in unit):
            x = datetime_time.replace(hour=0,minute=0,second=0).timestamp()
        elif ("mon" in unit):
            x = datetime_time.replace(day=1,hour=0,minute=0,second=0).timestamp()
        elif (unit == "y" or "yr" in unit or "year" in unit):
            x = datetime_time.replace(month=1,day=1,hour=0,minute=0,second=0).timestamp()
        elif ("w" in unit):
            day = datetime_time.weekday()
            x = datetime_time-datetime.timedelta(days=day).timestamp()
        else:
            raise Exception("Error parsing snap unit; no match for unit")
        
        self.time_calculated = x

    def _apply_offset(self, offset:str, unit:str):
        """This function is used to apply the offset to a given time and unit
        This can be in 3 places in the pattern
        <offset 1><offset 2>@<snap><snap offset> // such as: -15m+5s@d+1h
        This function handles one offset at a time and does not matter which offset it is

        Args:
            offset (string): Offset to apply
            unit (string): Represents the unit on which applying the offset

        Raises:
            Exception: Generic exception raised in case of a non supported case
        """
        # No need to convert to datetime in this function (exception month)
        # Just add or subtract the appropriate number of seconds
        if (offset == None or unit == None):
            x = self.time_calculated
        elif (unit == "s" or "sec" in unit):
            x = self.time_calculated + int(offset)
        elif (unit == "m" or "min" in unit):
            x = self.time_calculated + int(offset)*60
        elif (unit == "h" or "hr" in unit or "hour" in unit):
            x = self.time_calculated + int(offset)*60*60
        elif (unit == "d" or "day" in unit):
            x = self.time_calculated + int(offset)*60*60*24
        elif ("w" in unit):
            x = self.time_calculated + int(offset)*60*60*24*7
        elif (unit == "y" or "yr" in unit or "year" in unit):
            x = self.time_calculated + int(offset)*60*60*24*7*365
        # Month is a special use case, since it is the only period that does not have a set number of seconds
        # To handle Month I convert to Datetime, and use relativedelta to add or subtract the number of months
        # then subtract epoch Datetime and get difference in seconds similar to applySnap
        elif ("mon" in unit):
            try:
                x = (datetime.datetime.fromtimestamp(int(self.time_calculated),tz=self.tz)+relativedelta(months=int(offset))).timestamp()
            except Exception as e:
                raise e
        else:
            raise Exception("Error applying time offset; no match for unit")
        
        self.time_calculated = x

    def _calculate_target_time(self):
        """This function will get earliest or latest based on the scheduled run time. This could be as simple as -15m or @d or be complex as -1mon@y+12d
        Inherited and refactored from the Splunk Rerun app
        """
        self.logger_file.debug("030","Relative time - Original time: {0} ({1}) will be processed with the given pattern: {2}".format(self.time_original,datetime.datetime.fromtimestamp(self.time_original,tz=self.tz).strftime("%c %z"),self.pattern.original_pattern))


        if self.pattern.original_pattern.isdigit():
            #If it is static time
            self.time_calculated = self.pattern.original_pattern
            self.datetime_calculated = datetime.datetime.fromtimestamp(float(self.pattern.original_pattern))
            self.logger_file.debug("034","Relative time - Result: {0} ({1})".format(self.time_calculated,datetime.datetime.fromtimestamp(float(self.time_calculated),tz=self.tz).strftime("%c %z")))
        
        elif self.pattern.original_pattern != "now":

            #Apply snap then offsets in the following order: snap offset, first offset, second offset
            #The only time I think the order of offset would matter is when "mon" is used.

            self._apply_snap(self.pattern.snap)
            self._apply_offset(self.pattern.snapOff, self.pattern.snapUnit)
            self._apply_offset(self.pattern.offset1, self.pattern.unit1)
            self._apply_offset(self.pattern.offset2, self.pattern.unit2)

            self.datetime_calculated = datetime.datetime.fromtimestamp(self.time_calculated)
            
            self.logger_file.debug("035","Relative time - Result: {0} ({1})".format(self.time_calculated,datetime.datetime.fromtimestamp(self.time_calculated,tz=self.tz).strftime("%c %z")))

        else:
            # We have a "now" timestamp. As value is already initialized with original time, return the original time
            self.datetime_calculated = datetime.datetime.fromtimestamp(self.time_calculated)
            self.logger_file.debug("036","Relative time - Result: {0} ({1})".format(self.time_original,self.datetime_calculated.strftime("%c %z")))

class Backlog(object):
    def __init__(self, name: str, lookup_file_name: str, lookup_headers: list, spl_token: str = None, logger: str = None):
        """ This function is used to initialize a Backlog object

        Args:
            name (str): Name of the backlog
            lookup_file_name (str): Name of the file lookup to use as a backlog
            lookup_headers (list): List of headers to use to initiate the lookup if empty
            spl_token (str, optional): _description_. Defaults to None.
            logger (str, optional): _description_. Defaults to None.
        """
        # Initialize all settings to None
        self.logger = logger
        self.logger_file = LoggerFile(logger, "B")
        self.namespace = "TA-detection-backfill"
        self.directory = os.path.join(os.environ['SPLUNK_HOME'], 'etc', 'apps', self.namespace, 'lookups')
        self.backlog_file_name = lookup_file_name
        self.backlog_file = os.path.join(self.directory, self.backlog_file_name)
        self.backlog_file_tmp = os.path.join(os.environ['SPLUNK_HOME'], 'var', 'run', 'splunk', 'lookup_tmp', "tmp_{0}_".format(random.randint(1,10000))+"_"+self.backlog_file_name)
        self.headers = sorted(lookup_headers)
        self.spl_service = client.Service(token=spl_token)

        # Create the file if it's not existing or empty (issue with headers not existing)
        if not os.path.exists(self.backlog_file) or os.path.getsize(self.backlog_file) == 0:
            self.create_lookup_backlog()

    def spl_post(self, uri=None, **query):
        r = json.loads(self.spl_service.post(uri, owner="nobody", app=self.namespace,**query).body.read())["entry"][0]["content"]
        return r

    def create_lookup_backlog(self):
        """ This function is used to create a backlog lookup if it doesn't exist """

        # if it does not exist, create detection_backfill_rerun_backlog.csv
        self.logger_file.info("005","Initialize backlog file: " + str(self.backlog_file))

        # file backlog_file.csv doesn't exist or misconfigured. Create the file
        try:
            if not os.path.exists(self.directory):
                os.makedirs(self.directory)
            with open(self.backlog_file, 'w') as file_object:
                writer = csv.DictWriter(file_object, fieldnames=self.headers)
                writer.writeheader()
        except IOError:
            self.logger_file.error("010","FATAL {} could not be opened in write mode".format(self.headers))

    def add(self, tasks = []) -> bool:
        """ This function is used to add a list of tasks to the backlog. Returns a boolean to know if tasks were added or not """
        check = True
        # Check that all tasks are matching the headers and are not empty
        for t in tasks:
            for h in self.headers:
                if h not in t:
                    check = False
                    self.logger_file.error("015","An issue was found with the task '{0}' not having one of the required headers: '{1}'".format(t,h))
            if not check:
                sys.exit(15)

        # Get the backlog and add new tasks
        backlog = self.get() + tasks

        # Write the results
        self.set(backlog)

        return check

    def get(self) -> list:
        """" This function is used to get all tasks from the backlog as a list of dictionnaries """
        outputs = []
        if os.path.exists(self.backlog_file):
            with open(self.backlog_file, 'r') as file:
                content = csv.reader(file)
                header = next(content)
                for line in content:
                    if line != []:
                        # Build the row as a dict
                        row = {}
                        for i in range(0,len(line)):
                            row[header[i]] = line[i]
                        outputs.append(row)
        self.logger_file.info("030","Backlog recovered: {0} tasks found".format(len(outputs)))
        return outputs
    
    def next_tasks(self, count = 1) -> list:
        """ This function is returning the next tasks from the backlog based on the provided counter (and remove also the entry from the backlog)"""
        tasks_todo = []
        tasks = self.get()
        original_tasks_count = len(tasks)
        if len(tasks) >= count:
            self.logger_file.debug("032","Backlog size ({size}) is bigger than the number of tasks to process ({count})".format(size=len(tasks),count=count))
            for i in range(0,count):
                task = tasks.pop(0)
                tasks_todo.append(task)
                self.logger_file.debug("033","Backlog recovered, got next task #{i}: {task}".format(i=i,task=task))
        elif len(tasks) > 0 and len(tasks) < count:
            self.logger_file.debug("034","Backlog size ({size}) is smaller than the number of tasks to process ({count})".format(size=len(tasks),count=count))
            for i in range(0,len(tasks)):
                task = tasks.pop(0)
                tasks_todo.append(task)
                self.logger_file.debug("035","Backlog recovered, got next task #{i}: {task}".format(i=i,task=task))
        if original_tasks_count > 0:
            tasks = self.set(tasks)
        return tasks_todo

    def set(self, tasks = []) -> bool:
        """ This function is used to set a list of tasks (overwrite) to the backlog. Returns a boolean to know if tasks were set or not"""
        check = True
        backlog_sorted = []
        # Sort the backlog if not empty
        if len(tasks) > 0:
            if "orig_exec_time" in tasks[0]:
                backlog_sorted = sorted(tasks, key=lambda d: (int(d['batch_priority']),int(d['orig_exec_time'])))
            else:
                backlog_sorted = sorted(tasks, key=lambda d: (int(d['batch_priority']),d['batch_name'])) 
        # Write the results if checks are successful
        try:
            with open(self.backlog_file_tmp, 'w', newline='') as file_object:
                writer = csv.DictWriter(file_object, fieldnames=self.headers)
                writer.writeheader()
                for task in backlog_sorted:
                    writer.writerow(task)
        except IOError:
            self.logger_file.error("040","FATAL {} could not be opened in write mode".format(self.headers))
        # Store results in the CSV file through the Splunk API for lookup replication
        query = {"eai:data": self.backlog_file_tmp, "output_mode": "json"}
        self.spl_post(uri="data/lookup-table-files/{0}".format(self.backlog_file_name),**query)
        self.logger_file.info("041","Backlog updated: {0} tasks written".format(len(backlog_sorted)))
        return check

class SPLCodeInjection(object):
    def __init__(self, spl_token=None, logger=None):
        # Initialize all settings to None
        self.logger = logger
        self.logger_file = LoggerFile(logger, "SPLCI")
        self.namespace = "TA-detection-backfill"
        self.directory = os.path.join(os.environ['SPLUNK_HOME'], 'etc', 'apps', self.namespace, 'lookups')
        self.spl_code_injection_file_name = "detection_backfill_spl_code_injections.csv"
        self.spl_code_injection_file = os.path.join(self.directory, self.spl_code_injection_file_name)
        self.headers = sorted(["id", "macro", "name", "position"])
        self.spl_service = client.Service(token=spl_token)

        # Create the file if it's not existing or empty (issue with headers not existing)
        if not os.path.exists(self.spl_code_injection_file) or os.path.getsize(self.spl_code_injection_file) == 0:
            self.create_lookup_spl_code_injection()

    def spl_post(self, uri=None, **query):
        r = json.loads(self.spl_service.post(uri, owner="nobody", app=self.namespace,**query).body.read())["entry"][0]["content"]
        return r

    def create_lookup_spl_code_injection(self):
        """ This function is used to create a SPL code injection lookup if it doesn't exist """

        # if it does not exist, create detection_backfill_spl_code_injections.csv
        self.logger_file.info("005","Initialize SPL code injection file: " + str(self.spl_code_injection_file))

        # file doesn't exist or misconfigured. Create the file
        try:
            if not os.path.exists(self.directory):
                os.makedirs(self.directory)
            with open(self.spl_code_injection_file, 'w') as file_object:
                writer = csv.DictWriter(file_object, fieldnames=self.headers)
                writer.writeheader()
                writer.writerow({"id": "0c6d1d97", "macro": "default_code_injection", "name": "Default code injection adding a new field 'backfill' set to 1 at the end of the search", "position": "-1"})
        except IOError:
            self.logger_file.error("010","FATAL {} could not be opened in write mode".format(self.headers))

    def get(self) -> dict:
        """" This function is used to get all SPL code injection settings from the corresponding CSV file as a dictionnary by id """
        outputs = {}
        if os.path.exists(self.spl_code_injection_file):
            with open(self.spl_code_injection_file, 'r') as file:
                content = csv.reader(file)
                header = next(content)
                for line in content:
                    if line != []:
                        # Build the row as a dict
                        row = {}
                        for i in range(0,len(line)):
                            row[header[i]] = line[i]
                        id = row["id"]
                        outputs[id] = row
        self.logger_file.debug("030","SPL code injections list recovered: {0} possibilities found".format(len(outputs)))
        return outputs


class Settings(object):

    def __init__(self, client: client = None, settings=None, logger=None):
        # Initialize all settings to None
        self.logger = logger
        self.logger_file = LoggerFile(logger, "S")
        self.backlog = []
        self.client = client
        self.namespace = "TA-detection-backfill"

        self._logging_settings = None
        self._additional_parameters = None

        # Prepare the query
        self.query = {"output_mode": "json"}
        if settings is not None:
            conf = self.read_default_local_configuration("ta_detection_backfill_settings.conf")
            # Get logging
            self._logging_settings = conf["logging"]
            # Set logging level
            logger.setLevel(self._logging_settings["loglevel"])
            # Get additional parameters
            self._additional_parameters = conf["additional_parameters"]
     
    @property
    def logging_settings(self):
        return self._logging_settings
    
    @property
    def additional_parameters(self):
        return self._additional_parameters

    def read_conf_file(self, folder, filename):
        """ This function is used to retrieve information from a .conf file stored in a specified folder in this application """
        conf = {}

        # Open and read the conf file
        conf_file = os.path.join(os.environ['SPLUNK_HOME'], 'etc', 'apps', self.namespace, folder, filename)
        if os.path.isfile(conf_file):
            with open(conf_file, 'r') as file:
                stanza = None
                for line in file:
                    if line.startswith("["):
                        # We have a new stanza
                        stanza = line.strip()[1:][:-1]
                        conf[stanza] = {}
                    if " = " in line:
                        # Build a dictionnary with the information
                        key, value = line.partition(" = ")[::2]
                        # Check if the key exist. If so, then create a list of detected values accordingly
                        skey = key.strip()
                        if skey in conf:
                            if type(conf[skey]) is list:
                                conf[stanza][skey] += [value.rstrip('\n')]
                            else:
                                conf[stanza][skey] = [value.rstrip('\n')] + [conf[skey]]
                        else:
                            conf[stanza][skey] = value.rstrip('\n')
            self.logger_file.debug("026","Configuration "+folder+"/"+filename+" found: "+str(conf))
        else:
            self.logger_file.debug("027","Configuration "+folder+"/"+filename+" doesn't exist.")
        return conf

    def read_default_local_configuration(self, filename):
        """ This function is used to retrieve information from a default/local configuration merged dictionnary where local is prior to default settings """

        # Open and read the default file
        default = self.read_conf_file('default', filename)
        # Do the same with the local file if it's existing and merge information
        local = self.read_conf_file('local', filename)

        # Recovered configuration for the filename
        self.logger_file.debug("030","Merged configuration retrieved for the filename '"+filename+"': "+str({**default, **local}))

        return {**default, **local}