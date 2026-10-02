---
name: hello-catch-me-up
description: "Sets up the catch-me-up skill for a person's first-ever use, or updates their existing catch-me-up settings (lookback window, connected apps, Slack channels to recap, fun add-on). Use when someone is setting up catch-me-up for the first time, wants to change any of its settings (\"change my catch-me-up window\", \"add Jira to my catch-me-up\", \"turn off the joke\", \"stop recapping that channel\"), or asks what catch-me-up can do. Do not use this to actually run a check, that's the catch-me-up skill."
---

# Hello, Catch Me Up

Setup and configuration for the `catch-me-up` skill, first-run interview, connecting apps, and changing settings later. This skill never runs a scan itself; when a check is due (first run, or a mixed request like "add Jira and catch me up"), it hands off to `catch-me-up` at the end.

## Step 1: Check for existing config

Config lives in this person's own memory, never in a shared or default file: `/areas/catch-me-up-config.md`.

- Found → skip to **Step 3 (Change a setting)** below, this is a reconfig, not first-run setup.
- Not found → this is first-run setup. Continue to **Step 2**.
- Memory tools not available in this environment → tell the person once that answers won't be remembered between sessions here, ask the same questions from Step 2 inline, and skip connection-offering (Step 2c) and the save in Step 4, proceed to Step 5 with the answers for this run only.

## Step 2: First-run interview

Ask with `ask_user_input_v0` if available (people are often on mobile, tapping beats typing); otherwise ask as plain questions in one message.

2a. **Lookback window**: "When you run a check without saying a time frame, how far back should I look by default?"
   Options: `1 hour`, `2 hours`, `8 hours (recommended default)`, `Something else`
   If "Something else," ask for the number of hours directly.

2b. **Apps to check**: "Gmail and Slack are checked by default. Anything else you want included?"
   Multi-select options: `Jira`, `Asana`, `Something else`, `Just Gmail + Slack`
   If "Something else," ask them to name the tool(s). Some people will want just Gmail + Slack, that's a complete, valid config.

2c. **Connect each app**: for every app chosen in 2b (plus Gmail/Slack), check whether a connected tool already exists for it. Do this before asking about channels below, since channel validation in 2d needs Slack already connected.
   - Already connected → nothing to do, move on.
   - Not connected → offer to connect it right now (search the registry, then suggest connecting). If they connect it, note the app as connected. If they decline, save the app with a nudge count of 1 (see **Ground rules** in `catch-me-up` for what happens on future runs) rather than 0, a decline during setup still counts as the first offer.

2d. **Slack channels to recap** (only if Slack is in their app list), "Beyond your DMs and @-mentions, is there a specific Slack channel (or a few) you want a 'what did I miss' recap of? Comma-separated is fine. Easiest way to get the name right: right-click the channel in Slack and choose Copy link (or Copy name), then paste it here." Make clear this is optional.

Validate every channel entry before saving:
1. Split on commas, trim whitespace from each piece.
2. If a piece is a URL (contains `slack.com/archives/`), pull the channel ID out of the path, that's an exact reference, no name-matching needed.
3. Otherwise, strip a leading `#` and treat the rest as a channel name to look up.
4. Confirm each one actually resolves using the connected Slack tool (list/search channels) before saving anything.
5. If an entry doesn't resolve, don't guess the closest match silently, tell the person exactly which entry failed (e.g. `"eng-updates"`, spelled as typed) and ask them to double check it or paste the channel link instead. Save only the entries that did resolve; don't block the rest of setup on one bad entry.

Save resolved channels by their stable ID where you have one (from a link), or by confirmed name otherwise, either way, store what the Slack tool actually confirmed, not the raw text the person typed.

2e. **Fun add-on**: "Want a little something extra at the end of each check, a joke, a quote, or a random fact? Or skip it?"
   Options: `Joke`, `Quote`, `Fun fact`, `No thanks`

Continue to **Step 4**.

## Step 3: Change a setting (config already exists)

Read the existing config. Figure out from the request which single thing is changing, a new app, a dropped app, a new/removed channel, a different default window, or the fun add-on preference, and ask only about that, using the same validation as Step 2 where relevant (e.g. a new channel still needs to resolve in Slack; a newly-added app still gets a connection offer per 2c). Don't re-run the rest of the interview.

If the request is genuinely unclear which setting it means, ask a clarifying question rather than guessing.

## Step 4: Save and confirm

Save the answers to `/areas/catch-me-up-config.md` (via `memory_write` on first run with `if_version: new`, or `memory_str_replace` for a targeted change) in this form:

```
---
name: catch-me-up-config
description: Personal config for the catch-me-up skill, default lookback window, apps to scan, fun add-on preference
sources: [chat]
---

- [stated] Default lookback window: 8 hours
- [stated] Apps to check: Gmail, Slack, Jira
- [stated] Slack channels to recap: #eng-updates, #product-launches
- [stated] Fun add-on: quote
```

(Only apps not connected carry a nudge note, e.g. `- Jira: not connected, offered 1x`, connected apps don't need a line beyond the "Apps to check" list.)

Confirm briefly in the person's own words (e.g. "Got it, 8-hour default, Gmail + Slack + Jira, and I'll toss in a quote each time.").

## Step 5: Hand off

- First-run setup, or a reconfig that was mixed with an explicit request to run a check right now ("add Jira and catch me up") → invoke `catch-me-up` starting at its Step 1, not Step 0, the settings change is already saved, so there's nothing left for its Step 0 to route back here. This also prevents a hand-off loop: without this, `catch-me-up`'s Step 0 would see the original request still "includes a settings change" and forward it back here again.
- A pure reconfig ask ("turn off the joke") → stop here. Don't run a check the person didn't ask for.
