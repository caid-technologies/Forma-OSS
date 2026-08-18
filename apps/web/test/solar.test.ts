import assert from "node:assert/strict";
import { test } from "node:test";

import {
  calculateSolarTimes,
  getDefaultLocationFromTimezone,
  getNextSolarTransition,
  PRESET_LOCATIONS,
  TIMEZONE_COORDINATES,
} from "../lib/solar";

test("calculates accurate sunrise and sunset for San Francisco on equinox", () => {
  const date = new Date(Date.UTC(2026, 2, 20, 19, 0, 0));
  const sfLat = 37.7749;
  const sfLng = -122.4194;

  const times = calculateSolarTimes(sfLat, sfLng, date);
  assert.equal(times.isPolarDay, false);
  assert.equal(times.isPolarNight, false);

  const sunriseUtcHour = times.sunrise.getUTCHours() + times.sunrise.getUTCMinutes() / 60;
  assert.ok(sunriseUtcHour >= 13.5 && sunriseUtcHour <= 15.0, `Sunrise UTC hour was ${sunriseUtcHour}`);

  const sunsetUtcHour = (times.sunset.getUTCHours() + times.sunset.getUTCMinutes() / 60 + 24) % 24;
  assert.ok(sunsetUtcHour >= 1.5 && sunsetUtcHour <= 3.0, `Sunset UTC hour was ${sunsetUtcHour}`);
});

test("accurately determines daylight vs night for midday and midnight", () => {
  const sfLat = 37.7749;
  const sfLng = -122.4194;

  // Midday local time (20:00 UTC = 13:00 PDT)
  const midday = new Date(Date.UTC(2026, 5, 21, 20, 0, 0));
  const dayTimes = calculateSolarTimes(sfLat, sfLng, midday);
  assert.equal(dayTimes.isDaylight, true);

  // Midnight local time (07:00 UTC = 00:00 PDT)
  const midnight = new Date(Date.UTC(2026, 5, 21, 7, 0, 0));
  const nightTimes = calculateSolarTimes(sfLat, sfLng, midnight);
  assert.equal(nightTimes.isDaylight, false);
});

test("correctly calculates next transition event and remaining milliseconds", () => {
  const sfLat = 37.7749;
  const sfLng = -122.4194;

  const midday = new Date(Date.UTC(2026, 5, 21, 19, 0, 0));
  const transition = getNextSolarTransition(sfLat, sfLng, midday);
  assert.equal(transition.nextEvent, "sunset");
  assert.ok(transition.msRemaining > 0);
  assert.ok(transition.msRemaining < 86400000);
});

test("timezone dictionary covers major global hubs", () => {
  assert.ok(TIMEZONE_COORDINATES["America/New_York"]);
  assert.ok(TIMEZONE_COORDINATES["Europe/London"]);
  assert.ok(TIMEZONE_COORDINATES["Asia/Tokyo"]);
  assert.ok(TIMEZONE_COORDINATES["America/Los_Angeles"]);
});

test("default location fallback provides valid coordinates and city", () => {
  const loc = getDefaultLocationFromTimezone();
  assert.ok(typeof loc.lat === "number" && !isNaN(loc.lat));
  assert.ok(typeof loc.lng === "number" && !isNaN(loc.lng));
  assert.ok(typeof loc.label === "string" && loc.label.length > 0);
});

test("preset locations list contains searchable cities", () => {
  assert.ok(PRESET_LOCATIONS.length >= 20);
  for (const preset of PRESET_LOCATIONS) {
    assert.ok(preset.name.length > 0);
    assert.ok(preset.lat >= -90 && preset.lat <= 90);
    assert.ok(preset.lng >= -180 && preset.lng <= 180);
  }
});
