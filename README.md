# The Optina Rule for Reading Scripture

A small static page that builds a repeating calendar for the Optina Monastery rule of daily Scripture reading.

Pick the day you will begin, and, if you are already partway through the Psalter, the kathisma to start from. The page shows the first week, then downloads an `.ics` file created in your browser. Nothing you choose is sent to a server.

The file contains **109 all-day events**:

- 89 Gospel and Apostol days. Day *d* starts on your start date plus *d − 1* days and repeats with `RRULE:FREQ=DAILY;INTERVAL=89`.
- 20 kathismata. Each one starts on the first day it falls and repeats with `RRULE:FREQ=DAILY;INTERVAL=20`.

There is no end date. Events are marked free (`TRANSP:TRANSPARENT`), have no alarms, and use stable ids so the same start date always produces the same events. Event text and Bible Hub links are copied verbatim from `data/rec/`.

## GitHub Pages

The site is plain HTML, CSS, and JavaScript at the repository root, so Pages can serve `main` with no build.

**https://jakobwrites.github.io/optina-reading-plan/**

In the repository: **Settings → Pages → Build and deployment → Deploy from a branch**. Branch: **main**. Folder: **/ (root)**. Save.

A `.nojekyll` file is included so Pages serves the files as they are.

## Use the calendar

Import the file into a **new calendar** used only for this plan (Google Calendar’s phone app cannot import a file; use a computer). The page has short steps for Google Calendar, Apple Calendar, and Outlook.

On an iPhone or iPad, the download is a `text/calendar` file. Safari should offer to add the events to Calendar.

To start on a different day, delete that calendar and import a new file. Importing the same file twice can create duplicates.

## Check the calendar file

```bash
python3 -m pip install icalendar
python3 test/verify_ics.py
```

The test runs `app.js` under Node for several start dates, including a leap day and a Psalter that begins at Kathisma 6. It checks that the file has 109 events, open-ended daily rules of 89 and 20 days, and that Day 1 and the chosen kathisma fall on the start date. Descriptions are compared with `data/rec/` after parsing with [icalendar](https://pypi.org/project/icalendar/).

## Source texts

`data/rec/g01.txt`–`g89.txt` and `k01.txt`–`k20.txt` are the event descriptions. Titles are taken from their first lines, for example `Day 1: Matthew 1 | Acts 1-2`, `Day 89: John 21 | Apostol complete`, and `Kathisma 6: Psalms 37-45`.

`readings.js` is that text in a form the page can load. After editing a source file, regenerate it:

```bash
python3 scripts/build_readings.py
```

Event ids look like `optina-day-01-from-20261022@optina-reading-plan` and `optina-kathisma-06-from-20261022-k06@optina-reading-plan`. They stay the same for a given start date and starting kathisma.

## Fonts

EB Garamond and Crimson Text are the Google Fonts families, included here under the SIL Open Font License so the page does not call out to Google. See `fonts/OFL-EBGaramond.txt` and `fonts/OFL-CrimsonText.txt`.
