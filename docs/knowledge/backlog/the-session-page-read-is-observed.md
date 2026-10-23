---
type: Backlog
title: The session page read is observed
description: the GET of a site's /app page that opens a WDK session is sent outside the request observer, so a budget a host keeps against on_wdk_request undercounts what it sends to the site.
tags: [wdk, transport, observer]
status: draft
---

# What is missing

`_init_wdk_session` (`wdk/_http.py`) sends `GET <site>/app` to obtain a `JSESSIONID`
through `client.send`, which bypasses the observer that reports every other WDK request.
Measured in one audit cost run on QA: 181 requests reported through `on_wdk_request` and
6 more `/app` sends that no observer saw, 3 for each run that read a target list. A host
that holds a per-site budget or a load limit against the observer counts fewer sends
than the site receives.

# Change

Report the session page read through the observer, as a WDK request with its own kind or
path, so a host can count it or leave it out by name.

# Done when

A unit test with a transport double counts the `/app` send in the observer's report, and
the request count of a run that opens a session equals the sends its transport saw.
