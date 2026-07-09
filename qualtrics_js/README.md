# Qualtrics JS

JavaScript snippets pasted into Qualtrics survey "JavaScript" question
blocks. These are what connect a Qualtrics survey page to the PRISM server
— without them, Qualtrics has no way to know who's taking the survey or to
tell PRISM a survey was finished.

Despite an older note in this file, this integration **is implemented and
in use** — every script below calls a live, working PRISM route.

## Files

- **`EMA_load_logic.js`** — runs when the EMA survey page loads. Asks PRISM
  whether this participant has already opened or completed today's survey,
  and shows the right status message.
- **`EMA_submit_logic.js`** — runs when the participant leaves the survey
  page. Tells PRISM the EMA survey is done for today.
- **`EMA_request_display_coords.js`** — runs on load; asks PRISM for the
  participant's location data and renders it as a small map inside the
  survey question (used for the GPS-related question(s)).
- **`recommendationLoad.js`** — runs on load for the feedback/recommendations
  survey; asks PRISM for that participant's personalized feedback and
  displays it in the question text.
- **`recommendationSubmit.js`** — runs when the participant leaves the
  feedback survey; tells PRISM the feedback survey was acknowledged.

## Setting these up in Qualtrics

Each script reads the participant's ID (and name, for the submit scripts)
from Qualtrics embedded data fields, so those fields need to be set on the
survey flow before these scripts will work.

**Important:** every script points at `http://localhost:5000/...` by
default. Before a survey goes live to real participants, whoever manages
the Qualtrics setup needs to swap that for whatever public address reaches
the running PRISM server in that deployment — and swap it back to
`localhost` before committing any changes back to this repo, since that
address is deployment-specific and shouldn't be checked in.
