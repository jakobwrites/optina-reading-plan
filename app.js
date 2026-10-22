/* Optina Rule calendar file, built entirely in the browser. */
(function (factory) {
  'use strict';

  var api = factory();

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
  }

  if (typeof window !== 'undefined') {
    window.OptinaPlan = api;
    var start = function () {
      try {
        var readings = typeof OPTINA_READINGS !== 'undefined' ? OPTINA_READINGS : window.OPTINA_READINGS;
        api.mount(readings);
      } catch (err) {
        var error = document.getElementById('form-error');
        if (error) error.textContent = 'The reading plan could not be loaded.';
        if (typeof console !== 'undefined') console.error(err);
      }
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', start);
    } else {
      start();
    }
  }
})(function () {
  'use strict';

  var encoder = new TextEncoder();

  function assertDate(iso) {
    if (typeof iso !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) {
      throw new Error('Choose a valid start date.');
    }
    var year = Number(iso.slice(0, 4));
    var month = Number(iso.slice(5, 7));
    var day = Number(iso.slice(8, 10));
    var dt = new Date(Date.UTC(year, month - 1, day));
    if (dt.getUTCFullYear() !== year || dt.getUTCMonth() !== month - 1 || dt.getUTCDate() !== day) {
      throw new Error('Choose a valid start date.');
    }
    return iso;
  }

  function assertKathisma(value) {
    var n = Number(value);
    if (!Number.isInteger(n) || n < 1 || n > 20) {
      throw new Error('Choose a kathisma from 1 to 20.');
    }
    return n;
  }

  function addDays(iso, days) {
    var dt = new Date(Date.UTC(
      Number(iso.slice(0, 4)),
      Number(iso.slice(5, 7)) - 1,
      Number(iso.slice(8, 10))
    ));
    dt.setUTCDate(dt.getUTCDate() + days);
    var month = String(dt.getUTCMonth() + 1).padStart(2, '0');
    var day = String(dt.getUTCDate()).padStart(2, '0');
    return dt.getUTCFullYear() + '-' + month + '-' + day;
  }

  function formatUtcStamp(date) {
    function pad(n) { return String(n).padStart(2, '0'); }
    return String(date.getUTCFullYear())
      + pad(date.getUTCMonth() + 1)
      + pad(date.getUTCDate())
      + 'T'
      + pad(date.getUTCHours())
      + pad(date.getUTCMinutes())
      + pad(date.getUTCSeconds())
      + 'Z';
  }

  function formatDisplay(iso) {
    var year = Number(iso.slice(0, 4));
    var month = Number(iso.slice(5, 7));
    var day = Number(iso.slice(8, 10));
    var dt = new Date(year, month - 1, day);
    return new Intl.DateTimeFormat(undefined, {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    }).format(dt);
  }

  function indexByNumber(list, count, label) {
    if (!list || list.length !== count) {
      throw new Error('Expected ' + count + ' ' + label + ' readings.');
    }
    var map = new Map();
    for (var i = 0; i < list.length; i++) {
      var item = list[i];
      if (!item || item.n !== i + 1 || typeof item.description !== 'string' || item.description === '') {
        throw new Error(label + ' readings must be numbered 1 to ' + count + ' in order.');
      }
      map.set(item.n, item);
    }
    return map;
  }

  function deriveDayTitle(n, description) {
    var gospel = null;
    var apostol = null;
    var lines = String(description).split('\n');
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (line.indexOf('Gospel: ') === 0) gospel = line.slice('Gospel: '.length);
      else if (line.indexOf('Apostol: ') === 0) apostol = line.slice('Apostol: '.length);
    }
    if (!gospel || !apostol) {
      throw new Error('Day ' + n + ' is missing a Gospel or Apostol line.');
    }
    if (apostol.indexOf('none') === 0) apostol = 'Apostol complete';
    return 'Day ' + n + ': ' + gospel + ' | ' + apostol;
  }

  function deriveKathismaTitle(description) {
    var first = String(description).split('\n')[0];
    var match = /^Psalter: Kathisma (\d+) \((Psalms? [^,]+)/.exec(first);
    if (!match) throw new Error('Unrecognized kathisma line: ' + first);
    return 'Kathisma ' + match[1] + ': ' + match[2];
  }

  function escapeIcsText(value) {
    return String(value)
      .replace(/\\/g, '\\\\')
      .replace(/\r\n/g, '\n')
      .replace(/\r/g, '\n')
      .replace(/\n/g, '\\n')
      .replace(/;/g, '\\;')
      .replace(/,/g, '\\,');
  }

  function icsChunks(line) {
    var chunks = [];
    for (var i = 0; i < line.length;) {
      if (line.charAt(i) === '\\' && i + 1 < line.length) {
        chunks.push(line.slice(i, i + 2));
        i += 2;
      } else {
        var cp = line.codePointAt(i);
        var ch = String.fromCodePoint(cp);
        chunks.push(ch);
        i += ch.length;
      }
    }
    return chunks;
  }

  /*
   * RFC 5545 folding: lines of at most 75 octets, continued with CRLF and
   * one space. Escapes stay intact. Breaks prefer a space or an escaped
   * newline so a Bible Hub link is not cut in half. Continuation lines
   * budget 74 octets, leaving room for that leading space.
   */
  function foldIcsLine(line) {
    var chunks = icsChunks(line);
    var parts = [];
    var index = 0;
    var limit = 75;

    while (index < chunks.length) {
      var octets = 0;
      var end = index;
      var lastSoft = index;
      while (end < chunks.length) {
        var size = encoder.encode(chunks[end]).length;
        if (octets + size > limit) break;
        octets += size;
        end += 1;
        if (chunks[end - 1] === ' ' || chunks[end - 1] === '\\n') lastSoft = end;
      }
      if (end === index) throw new Error('ICS value cannot be folded.');

      // When the rest does not fit, step back to the last space or
      // escaped newline so a link stays on one physical line.
      var cut = (end < chunks.length && lastSoft > index) ? lastSoft : end;
      parts.push(chunks.slice(index, cut).join(''));
      index = cut;
      limit = 74;
    }
    return parts.join('\r\n ');
  }

  function buildIcs(readings, options) {
    options = options || {};
    var startDate = assertDate(options.startDate);
    var startKathisma = assertKathisma(options.startKathisma == null ? 1 : options.startKathisma);
    var dtstamp = options.dtstamp || formatUtcStamp(new Date());
    if (!/^\d{8}T\d{6}Z$/.test(dtstamp)) throw new Error('Bad DTSTAMP.');

    var days = indexByNumber(readings.days, 89, 'Day');
    var kathismata = indexByNumber(readings.kathismata, 20, 'Kathisma');
    var startStamp = startDate.replace(/-/g, '');
    var calName = startKathisma === 1
      ? 'Optina Rule (from ' + startDate + ')'
      : 'Optina Rule (from ' + startDate + ', Kathisma ' + startKathisma + ')';
    var calDesc = 'Optina Rule daily Scripture. Gospel and Apostol repeat every 89 days from '
      + startDate + '. The Psalter repeats every 20 days, beginning with Kathisma ' + startKathisma + '.';

    var out = '';
    function push(line) {
      out += foldIcsLine(line) + '\r\n';
    }

    push('BEGIN:VCALENDAR');
    push('VERSION:2.0');
    push('PRODID:-//Optina Rule Reading Plan//EN');
    push('CALSCALE:GREGORIAN');
    push('METHOD:PUBLISH');
    push('NAME:' + escapeIcsText(calName));
    push('X-WR-CALNAME:' + escapeIcsText(calName));
    push('X-WR-CALDESC:' + escapeIcsText(calDesc));

    for (var n = 1; n <= 89; n++) {
      var dayDate = addDays(startDate, n - 1);
      var title = deriveDayTitle(n, days.get(n).description);
      push('BEGIN:VEVENT');
      push('UID:optina-day-' + pad2(n) + '-from-' + startStamp + '@optina-reading-plan');
      push('DTSTAMP:' + dtstamp);
      push('DTSTART;VALUE=DATE:' + dayDate.replace(/-/g, ''));
      push('DTEND;VALUE=DATE:' + addDays(dayDate, 1).replace(/-/g, ''));
      push('RRULE:FREQ=DAILY;INTERVAL=89');
      push('SUMMARY:' + escapeIcsText(title));
      push('DESCRIPTION:' + escapeIcsText(days.get(n).description));
      push('TRANSP:TRANSPARENT');
      push('X-MICROSOFT-CDO-BUSYSTATUS:FREE');
      push('END:VEVENT');
    }

    for (var k = 1; k <= 20; k++) {
      var offset = (k - startKathisma + 20) % 20;
      var kDate = addDays(startDate, offset);
      var kTitle = deriveKathismaTitle(kathismata.get(k).description);
      var found = Number(/^Kathisma (\d+)/.exec(kTitle)[1]);
      if (found !== k) throw new Error('Kathisma ' + k + ' title does not match its number.');
      push('BEGIN:VEVENT');
      push('UID:optina-kathisma-' + pad2(k) + '-from-' + startStamp + '-k' + pad2(startKathisma) + '@optina-reading-plan');
      push('DTSTAMP:' + dtstamp);
      push('DTSTART;VALUE=DATE:' + kDate.replace(/-/g, ''));
      push('DTEND;VALUE=DATE:' + addDays(kDate, 1).replace(/-/g, ''));
      push('RRULE:FREQ=DAILY;INTERVAL=20');
      push('SUMMARY:' + escapeIcsText(kTitle));
      push('DESCRIPTION:' + escapeIcsText(kathismata.get(k).description));
      push('TRANSP:TRANSPARENT');
      push('X-MICROSOFT-CDO-BUSYSTATUS:FREE');
      push('END:VEVENT');
    }

    push('END:VCALENDAR');
    return out;
  }

  function pad2(n) {
    return String(n).padStart(2, '0');
  }

  function previewDays(readings, options) {
    options = options || {};
    var startDate = assertDate(options.startDate);
    var startKathisma = assertKathisma(options.startKathisma == null ? 1 : options.startKathisma);
    var count = options.count == null ? 7 : options.count;
    if (!Number.isInteger(count) || count < 1 || count > 89) {
      throw new Error('Preview length is out of range.');
    }
    var days = indexByNumber(readings.days, 89, 'Day');
    var kathismata = indexByNumber(readings.kathismata, 20, 'Kathisma');
    var out = [];
    for (var i = 0; i < count; i++) {
      var n = (i % 89) + 1;
      var k = ((startKathisma - 1 + i) % 20) + 1;
      var title = deriveDayTitle(n, days.get(n).description);
      var kTitle = deriveKathismaTitle(kathismata.get(k).description);
      var rest = title.slice(('Day ' + n + ': ').length);
      var bar = rest.indexOf(' | ');
      if (bar < 0) throw new Error('Title is missing a divider.');
      out.push({
        date: addDays(startDate, i),
        dayNumber: n,
        gospel: rest.slice(0, bar),
        apostol: rest.slice(bar + 3),
        kathismaNumber: k,
        kathismaTitle: kTitle,
        title: title
      });
    }
    return out;
  }

  function isIOS() {
    var ua = navigator.userAgent || '';
    if (/iPad|iPhone|iPod/.test(ua)) return true;
    /* iPadOS 13+ reports a desktop Mac user agent. */
    return navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1;
  }

  /*
   * Desktop: a file download named .ics.
   * iPhone/iPad Safari: navigate to a text/calendar blob (no download
   * attribute). Safari then offers to add the events to Calendar.
   * The download attribute on iOS saves a file instead of that prompt.
   */
  function saveCalendarFile(filename, ics) {
    var file = new File([ics], filename, { type: 'text/calendar' });
    var url = URL.createObjectURL(file);
    if (isIOS()) {
      var opened = window.open(url, '_blank');
      if (!opened) window.location.assign(url);
      return;
    }
    var link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.rel = 'noopener';
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(function () { URL.revokeObjectURL(url); }, 4000);
  }

  function renderDay(day) {
    var li = document.createElement('li');

    var when = document.createElement('p');
    when.className = 'when';
    var num = document.createElement('span');
    num.className = 'daynum';
    num.textContent = 'Day ' + day.dayNumber;
    var time = document.createElement('time');
    time.dateTime = day.date;
    time.textContent = formatDisplay(day.date);
    when.appendChild(num);
    when.appendChild(document.createTextNode(' '));
    when.appendChild(time);

    var pericope = document.createElement('p');
    pericope.className = 'pericope';
    var gospel = document.createElement('span');
    gospel.className = 'gospel';
    gospel.textContent = day.gospel;
    var spoken = document.createElement('span');
    spoken.className = 'visually-hidden';
    spoken.textContent = ', ';
    var sep = document.createElement('span');
    sep.className = 'sep';
    sep.setAttribute('aria-hidden', 'true');
    sep.textContent = ' · ';
    var apostol = document.createElement('span');
    apostol.className = 'apostol' + (day.apostol === 'Apostol complete' ? ' complete' : '');
    apostol.textContent = day.apostol;
    pericope.appendChild(gospel);
    pericope.appendChild(spoken);
    pericope.appendChild(sep);
    pericope.appendChild(apostol);

    var psalter = document.createElement('p');
    psalter.className = 'psalter';
    psalter.textContent = day.kathismaTitle;

    li.appendChild(when);
    li.appendChild(pericope);
    li.appendChild(psalter);
    return li;
  }

  function mount(readings) {
    var form = document.getElementById('plan-form');
    var dateInput = document.getElementById('start-date');
    var kathismaSelect = document.getElementById('start-kathisma');
    var preview = document.getElementById('preview');
    var error = document.getElementById('form-error');
    var status = document.getElementById('download-status');
    var button = document.getElementById('download');
    var kathismaList = document.getElementById('kathisma-list');

    if (!readings) throw new Error('Readings are missing.');
    var kathismata = indexByNumber(readings.kathismata, 20, 'Kathisma');
    indexByNumber(readings.days, 89, 'Day');

    var options = [];
    for (var k = 1; k <= 20; k++) {
      var title = deriveKathismaTitle(kathismata.get(k).description);
      var opt = document.createElement('option');
      opt.value = String(k);
      opt.textContent = title;
      if (k === 1) opt.selected = true;
      options.push(opt);

      var li = document.createElement('li');
      var strong = document.createElement('strong');
      strong.textContent = 'K' + k;
      var span = document.createElement('span');
      span.textContent = title.replace(/^Kathisma \d+:\s*/, '');
      li.appendChild(strong);
      li.appendChild(span);
      kathismaList.appendChild(li);
    }
    kathismaSelect.replaceChildren.apply(kathismaSelect, options);

    if (!dateInput.value) dateInput.value = todayISO();

    function current() {
      return {
        startDate: dateInput.value,
        startKathisma: kathismaSelect.value
      };
    }

    function render() {
      error.textContent = '';
      status.textContent = '';
      preview.replaceChildren();
      var days;
      try {
        days = previewDays(readings, {
          startDate: current().startDate,
          startKathisma: current().startKathisma,
          count: 7
        });
      } catch (err) {
        error.textContent = err.message;
        button.disabled = true;
        return;
      }
      button.disabled = false;
      for (var i = 0; i < days.length; i++) preview.appendChild(renderDay(days[i]));
    }

    function download(event) {
      event.preventDefault();
      error.textContent = '';
      status.textContent = '';
      var chosen;
      var ics;
      try {
        chosen = current();
        chosen.startDate = assertDate(chosen.startDate);
        chosen.startKathisma = assertKathisma(chosen.startKathisma);
        ics = buildIcs(readings, chosen);
      } catch (err) {
        error.textContent = err.message;
        button.disabled = true;
        return;
      }
      var filename = 'optina-rule-' + chosen.startDate;
      if (chosen.startKathisma !== 1) filename += '-kathisma-' + chosen.startKathisma;
      filename += '.ics';
      saveCalendarFile(filename, ics);
      status.textContent = 'Calendar file ready: ' + filename;
    }

    dateInput.addEventListener('input', render);
    dateInput.addEventListener('change', render);
    kathismaSelect.addEventListener('change', render);
    form.addEventListener('submit', download);

    render();
  }

  function todayISO() {
    var now = new Date();
    var month = String(now.getMonth() + 1).padStart(2, '0');
    var day = String(now.getDate()).padStart(2, '0');
    return now.getFullYear() + '-' + month + '-' + day;
  }

  return {
    buildIcs: buildIcs,
    previewDays: previewDays,
    deriveDayTitle: deriveDayTitle,
    deriveKathismaTitle: deriveKathismaTitle,
    mount: mount
  };
});
