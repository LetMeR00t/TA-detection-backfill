<p align="center">
  <img src="https://github.com/LetMeR00t/TA-detection-backfill/blob/main/images/logo.png?raw=true" alt="Logo TA-detection-backfill"/>
</p>

- [Introduction](#introduction)
  - [Problem to solve](#problem-to-solve)
  - [Consequences](#consequences)
- [Use Cases](#use-cases)
- [Installation \& Configuration](#installation--configuration)
  - [Logging](#logging)
- [Usage](#usage)
  - [Detection Rerun](#detection-rerun)
    - [Create a backfill batch](#create-a-backfill-batch)
      - [From the dashboard](#from-the-dashboard)
      - [From any search using a custom command and custom alert action](#from-any-search-using-a-custom-command-and-custom-alert-action)
    - [Backlog](#backlog)
    - [Scheduling of re-runs](#scheduling-of-re-runs)
  - [Detection Healthcheck](#detection-healthcheck)
    - [Example: Savedsearch job execution](#example-savedsearch-job-execution)
    - [Example: Healthcheck job running with an additional scanned events (but not matching the search query)](#example-healthcheck-job-running-with-an-additional-scanned-events-but-not-matching-the-search-query)
    - [Example: Healthcheck job running with an additional scanned events (and matching the search query without changing the results count)](#example-healthcheck-job-running-with-an-additional-scanned-events-and-matching-the-search-query-without-changing-the-results-count)
    - [Example: Healthcheck job running with an additional scanned events (and matching the search query with an impact on the results count)](#example-healthcheck-job-running-with-an-additional-scanned-events-and-matching-the-search-query-with-an-impact-on-the-results-count)
    - [Example: Healthcheck job running without any change on the available events](#example-healthcheck-job-running-without-any-change-on-the-available-events)
- [Credits](#credits)
- [License](#license)

# Introduction

## Problem to solve

This TA can be used to **fill in detection gaps following a period of data collection interruption/disruption**.
Several scenarios can be overseen:

- **Scenario 1**: Log collection was stopped due to an issue between a datasource and Splunk. An outage period means that we didn't got the data in Splunk resulting in a loss of logs.

![Context - Log collection disruption](./images/context_outage_period.png)

- **Scenario 2**: Log collection is delayed due to an issue between a datasource and Splunk. Data are collected but with a significant difference between the **time the event (called "time" in the diagrams or the field "_time" in Splunk)** occurred (and a log was created on the data source) and the **time the log is indexed ("called "index time" in the diagrams or the field "_index_time" in Splunk)** in Splunk.

![Context - Log collection delay](./images/context_log_collection_delay.png)

## Consequences

As a result of the previous scenarios, detections might not be working properly as the data weren't available at the time of the search.

For the scenario 1, it results as:
![Context - Savedsearches not running properly for scenario 1](./images/context_savedsearch_not_running_properly_scenario1.png)

For the scenario 2, it results as:
![Context - Savedsearches not running properly for scenario 2](./images/context_savedsearch_not_running_properly_scenario2.png)

Detection backfill naming is a reference to the data backfilling process which aims to recover old data to fill gaps. As we are focusing on re-running savedsearches or correlation searches, we are talking about detection backfilling.

# Use Cases

The objective is to provide an easy way to relaunch savedsearches (or correlation searches) on an outage period of time when data weren't available (either not collected at all or not indexed in time). As soon as you have retrieved your data, you might want to re-run your detections over those old periods of time that didn't ran correctly as data weren't fully available.

However, whatever is the outage period range, **we don't want to impact the performances of the Splunk infrastructure** if we need to re-run old detections. In order to respect this, this application is based on a backlog that will be used to process re-runs progressively and not everything them all at once.

This application can interest you if you are looking for:

- A way to re-run savedsearches or correlation searches easily on past data after an outage period of data collection
- A way to re-run savedsearches or correlation searches easily when you detect an anomaly in your detections that could have miss some interesting events in the past

As we build up the individual savedsearches so that they are rerun in the same context as they should have been run, this means that you can reschedule these searches, even over large periods, as the backlog will be filled with all the time slots that need to be covered. Even if thousands of time slots are created in the backlog, they will be processed progressively at the speed at which you want them to run.

# Installation & Configuration

This application doesn't require any specific installation setup to be running as it's based on Splunk core functionalities. It can be installed and used as is.

## Logging

You can enable a "debug" logging mode (under **Configuration**) to have more information in searches/logs.
By default, all logging files are created under `$SPLUNK_HOME/var/log/splunk/`

You will be able to have these logs in your search.log too.

**A dedicated dashboard named "Audit logs" is available in the app** to track all the logs generated by the application itself. If any issue is happening with the application, you can rely on this dashboard to investigate the problem.

![Audit logs 1](images/audit_logs_1.png)
*Example of the audit logs dashboard (1)*

![Audit logs 2](images/audit_logs_2.png)
*Example of the audit logs dashboard (2)*

# Usage

## Detection Rerun

Once data are recovered in Splunk, this application can be used to restart scheduled searches during this outage.

For the scenario 1, it results as:
![Context - Savedsearches rerun for scenario 1](./images/context_savedsearch_rerun_scenario1.png)

For the scenario 2, it results as:
![Context - Savedsearches rerun for scenario 2](./images/context_savedsearch_rerun_scenario2.png)

### Create a backfill batch

#### From the dashboard

![Create detection backfill](images/create_detection_backfill.png)
*Dashboard: Create a detection backfill*

This dashboard is helping you to generate a list of re-runs based on an outage period and a regular expression to know which savedsearches must be taken into account (disabled and non-schedule savedsearches aren't taken into consideration)

You can use the two input fields on the first panel named "1. Calculate all (re)dispatch times" to generate all the detections matching the regular expression to be re-run by dispatch time to cover the outage period.

If you feel confortable with the provided results, you can create a new batch on the second panel named "2. Add results to the backlog for processing" using the two inputs to provide a name for your batch and a priority. Priority is used to evaluate when the re-run must be done. Highest (0) priorities will be managed in prior of other priorities.

The priority order is:

`Highest(0) > High (1) > Medium (2) > Low (3) > Lowest (4)`

For example, if you create a batch with a priority "High (1)" and an existing batch is already existing in the backlog with a priority "Medium (2)", the new created batch will be processed in priority.

#### From any search using a custom command and custom alert action

Actually, the dashboard is using a custom command to generate all the re-run.
You can use the command as this:

```python
... (search)
| script backfill_detection_evaluate_savedsearches_to_rerun
```

This script is expecting to have events with three fields:

- **outage_period_earliest**: Indicates the earliest time of the outage period
- **outage_period_latest**: Indicates the latest time of the outage period
- **savedsearches_regex**: Indicates the regular expression to apply on the savedsearches to know if need to consider them or not (disabled and non-schedule savedsearches aren't taken into consideration)

If you provide several events to the script, it will process each event indenpendently and return all the results at once.

In order to add new backfills into the backlog, you can rely on a custom alert action to help you:

![Custom alert action: Add a backfill to the backlog](images/custom_alert_action_add_backfill_to_backlog.png)
*Custom alert action: Add a backfill to the backlog*

### Backlog

![Backlog](images/backlog.png)
*Dashboard: Manage the backlog*

This dashboard is used to list the backlog tasks and see the order of all detections to be re-run.

Each time a new batch is added to the backlog, it's sorted by "Batch priority" (Minor values are more prior) then by the "Savedsearch name" (alphabetical order)

In this dashboard, you can list all re-runs or delete one of the savedsearch re-run.

### Scheduling of re-runs

![Run the next scheduled detection backfill](images/custom_alert_action_rerun.png)
*Savedsearch: Run the next scheduled detection backfill and Custom alert action: Run the next backfill*

Re-runs scheduling is made using a dedicated scheduled savedsearch in the application named "Run the next scheduled detection backfill". This savedsearch is generated as many events as we want to re-run backfills from the backlog at the same time (2 by default).

A custom alert action named "Run the next backfill" is executed to process as many tasks in the backlog as events from the search.

> **Note**: As you can see, you can select if you want (or not) execute the triggers of your savedsearches if the trigger condition is met. If yes, then all trigger actions (custom alert actions) will be executed as soon as the re-run job is finished.

## Detection Healthcheck

In this application, you have the possibility to monitor your savedsearches and check if, after a certain period of time, we still have the same behavior by running a `healthcheck job`. A `healthcheck job` is simply the same search (query, earliest/latest time, etc) run again after a certain period of time **on the same timeslot than the original execution**, it's then used to check if we have the exact behavior and results regarding the original search. If some logs were missing during the original execution, we will have a different behavior and possibly results.

A `healthcheck job` is monitoring/checking those information:

- **Scans count**: Represent the total number of events that were scanned by the search query (index/sourcetype)
- **Events count**: Represent the total number of events that were returned by the indexers (matching events) based on the search query (index/sourcetype). Those events are then used by the rest of the search query to be processed.
- **Results count**: Represent the total number of results returned by the savedsearch after processing the data.

### Example: Savedsearch job execution

Here is an example about a savedsearch named `SS1` which is executing a search query on the below indexers:
![Detection Healthcheck - Scans/Events/Results explanation](./images/detection_healthcheck_scans_events_results_explanation.png)

In the above example, we can see:

- **Scans count**: We are scanning `index=I1` and `index=I3` which contains respectively 6 and 5 events in total. Total scans count is 11.
- **Events count**: As the query is searching only on events with a field "id", we can see that `index=I1 sourcetype=S1` contains 3 events and `index=I3` contains 4 events with this condition. Total events count is 7.
- **Results count**: As the query is doing a stats on the number of sourcetypes and that at least one event exists in the sourcetypes `S1 (in I1 and I3)` and `S4 (in I3)`, total results count is 2.

### Example: Healthcheck job running with an additional scanned events (but not matching the search query)

Let's assume in this example that we perform a healthcheck job after 12 hours knowing that:

- 3 new events were recovered after the savedsearch execution and should have been considered at the time of the search
- Those events aren't matching the search query (and thus, don't change the results count)

Let's imagine how the healthcheck job will run:

![Detection Healthcheck - Additional events with no impact on returned events or results](./images/detection_healthcheck_example_1.png)

We have now 14 scanned events instead of 11. A warning will be shown in a dedicated dashboard for this search as it's not expected to have additional events after the execution of the savedsearch on the same period of time. However, as there is no impact on the events count or results count, this wasn't a major issue after all as the savedsearch didn't provide anything new.

### Example: Healthcheck job running with an additional scanned events (and matching the search query without changing the results count)

Let's assume in this example that we perform a healthcheck job after 12 hours knowing that:

- 3 new events were recovered after the savedsearch execution and should have been considered at the time of the search
- 1 of those events is matching the search query
- Those events don't impact the results count

Let's imagine how the healthcheck job will run:

![Detection Healthcheck - Additional events with impact on returned events but not on results](./images/detection_healthcheck_example_2.png)

We have now 8 events returned by the indexers instead of 7. A warning will be shown in a dedicated dashboard for this search as it's not expected to have additional events after the execution of the savedsearch on the same period of time. However, as there is no impact on the results count, this wasn't a major issue after all as the savedsearch didn't provide anything new. Still, it's important to notice that this issue is more serious than the previous example as it could have lead to a direct impact on the savedsearch results.

> ⚠️ We are checking only the number of results, not the content. This means that additional returned events can have an impact on the results content without necessarely modifying the content.

### Example: Healthcheck job running with an additional scanned events (and matching the search query with an impact on the results count)

Let's assume in this example that we perform a healthcheck job after 12 hours knowing that:

- 3 new events were recovered after the savedsearch execution and should have been considered at the time of the search
- 1 of those events is matching the search query
- This event is impacting the results count

Let's imagine how the healthcheck job will run:

![Detection Healthcheck - Additional events with impact on returned events and results](./images/detection_healthcheck_example_3.png)

We have now 3 results instead of 2. A failed message will be shown in a dedicated dashboard for this search as it's not expected to have a different number of results after the execution of the savedsearch on the same period of time. This is the most critical scenario when additional events indexed after the original search have a direct impact on the results count. In this case, it would be better to dispatch again the savedsearch on the given period and trigger again the alerts actions (and this could be done with the "rerun" feature of this application).

> ⚠️ Again, we are checking only the number of results, not the content. This means that additional returned events can have an impact on the results content in addition to the number of results.

### Example: Healthcheck job running without any change on the available events

In this situation, we have the exact same behavior than the original search. It means that nothing changed and that the original search didn't have any issue afterall. This will be indicated through a successful healthcheck job result.

# Credits

This application was largely inspired from the [Splunk rerun app](https://github.com/murchisd/splunk_rerun_app) made by Donald Murchison

[Repeat icons created by Freepik - Flaticon](https://www.flaticon.com/free-icons/repeat)

# License

MIT License

Copyright (c) 2023 LmR

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
