/**
 * Solar position and sunrise/sunset calculation based on the NOAA / astronomical algorithm.
 * Operates in pure JavaScript with zero external dependencies, computing accurate local
 * sunrise, sunset, and daylight status for any latitude and longitude.
 */

export interface SolarTimes {
  sunrise: Date;
  sunset: Date;
  solarNoon: Date;
  isDaylight: boolean;
  isPolarDay: boolean;
  isPolarNight: boolean;
}

export interface SolarTransition {
  nextEvent: "sunrise" | "sunset";
  nextTime: Date;
  msRemaining: number;
}

const RAD = Math.PI / 180;
const DEG = 180 / Math.PI;
const ZENITH_SUNRISE_SUNSET = 90.833; // Standard refraction (34 arcmin) + solar semi-diameter (16 arcmin)

function sinDeg(d: number): number {
  return Math.sin(d * RAD);
}

function cosDeg(d: number): number {
  return Math.cos(d * RAD);
}

function dateToJulian(date: Date): number {
  return date.getTime() / 86400000 + 2440587.5;
}

function julianToDate(jd: number): Date {
  return new Date((jd - 2440587.5) * 86400000);
}

/**
 * Calculates sunrise, sunset, solar noon, and daylight status for a given coordinate and date.
 */
export function calculateSolarTimes(lat: number, lng: number, date: Date = new Date()): SolarTimes {
  const utcMidnight = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), 0, 0, 0));
  const jdMidnight = dateToJulian(utcMidnight);

  const d = jdMidnight - 2451545.0 + 0.0008;

  const nStar = d - lng / 360;
  const n = Math.round(nStar);
  const jStar = 2451545.0 + n + 0.0008 - lng / 360;

  const m = (357.5291 + 0.98560028 * (jStar - 2451545.0)) % 360;
  const mNorm = m < 0 ? m + 360 : m;

  const c = 1.9148 * sinDeg(mNorm) + 0.02 * sinDeg(2 * mNorm) + 0.0003 * sinDeg(3 * mNorm);

  const lambda = (mNorm + c + 180 + 102.9372) % 360;
  const lambdaNorm = lambda < 0 ? lambda + 360 : lambda;

  const jTransit = jStar + 0.0053 * sinDeg(mNorm) - 0.0069 * sinDeg(2 * lambdaNorm);
  const solarNoon = julianToDate(jTransit);

  const sinDelta = sinDeg(lambdaNorm) * sinDeg(23.44);
  const cosDelta = Math.sqrt(Math.max(0, 1 - sinDelta * sinDelta));

  const cosH0 = (cosDeg(ZENITH_SUNRISE_SUNSET) - sinDeg(lat) * sinDelta) / (cosDeg(lat) * cosDelta);

  if (cosH0 >= 1) {
    return {
      sunrise: new Date(solarNoon.getTime() - 43200000),
      sunset: new Date(solarNoon.getTime() - 43200000),
      solarNoon,
      isDaylight: false,
      isPolarDay: false,
      isPolarNight: true,
    };
  }

  if (cosH0 <= -1) {
    return {
      sunrise: new Date(solarNoon.getTime() - 43200000),
      sunset: new Date(solarNoon.getTime() + 43200000),
      solarNoon,
      isDaylight: true,
      isPolarDay: true,
      isPolarNight: false,
    };
  }

  const h0Deg = Math.acos(cosH0) * DEG;
  const jRise = jTransit - h0Deg / 360;
  const jSet = jTransit + h0Deg / 360;

  const sunrise = julianToDate(jRise);
  const sunset = julianToDate(jSet);

  const currentTime = date.getTime();
  const isDaylight = currentTime >= sunrise.getTime() && currentTime < sunset.getTime();

  return {
    sunrise,
    sunset,
    solarNoon,
    isDaylight,
    isPolarDay: false,
    isPolarNight: false,
  };
}

export function getNextSolarTransition(lat: number, lng: number, date: Date = new Date()): SolarTransition {
  const current = calculateSolarTimes(lat, lng, date);
  const now = date.getTime();

  if (current.isPolarDay || current.isPolarNight) {
    const tomorrow = new Date(date.getTime() + 86400000);
    return {
      nextEvent: current.isPolarDay ? "sunset" : "sunrise",
      nextTime: tomorrow,
      msRemaining: 86400000,
    };
  }

  if (now < current.sunrise.getTime()) {
    return {
      nextEvent: "sunrise",
      nextTime: current.sunrise,
      msRemaining: current.sunrise.getTime() - now,
    };
  }

  if (now >= current.sunrise.getTime() && now < current.sunset.getTime()) {
    return {
      nextEvent: "sunset",
      nextTime: current.sunset,
      msRemaining: current.sunset.getTime() - now,
    };
  }

  const tomorrow = new Date(date.getTime() + 86400000);
  const tomorrowTimes = calculateSolarTimes(lat, lng, tomorrow);
  return {
    nextEvent: "sunrise",
    nextTime: tomorrowTimes.sunrise,
    msRemaining: tomorrowTimes.sunrise.getTime() - now,
  };
}

export const TIMEZONE_COORDINATES: Record<string, { lat: number; lng: number; city: string }> = {
  "America/New_York": { lat: 40.7128, lng: -74.006, city: "New York, USA" },
  "America/Detroit": { lat: 42.3314, lng: -83.0458, city: "Detroit, USA" },
  "America/Chicago": { lat: 41.8781, lng: -87.6298, city: "Chicago, USA" },
  "America/Denver": { lat: 39.7392, lng: -104.9903, city: "Denver, USA" },
  "America/Phoenix": { lat: 33.4484, lng: -112.074, city: "Phoenix, USA" },
  "America/Los_Angeles": { lat: 34.0522, lng: -118.2437, city: "Los Angeles, USA" },
  "America/Anchorage": { lat: 61.2181, lng: -149.9003, city: "Anchorage, USA" },
  "Pacific/Honolulu": { lat: 21.3069, lng: -157.8583, city: "Honolulu, USA" },
  "America/Toronto": { lat: 43.6532, lng: -79.3832, city: "Toronto, Canada" },
  "America/Vancouver": { lat: 49.2827, lng: -123.1207, city: "Vancouver, Canada" },
  "America/Mexico_City": { lat: 19.4326, lng: -99.1332, city: "Mexico City, Mexico" },
  "America/Sao_Paulo": { lat: -23.5505, lng: -46.6333, city: "São Paulo, Brazil" },
  "America/Buenos_Aires": { lat: -34.6037, lng: -58.3816, city: "Buenos Aires, Argentina" },
  "Europe/London": { lat: 51.5074, lng: -0.1278, city: "London, UK" },
  "Europe/Dublin": { lat: 53.3498, lng: -6.2603, city: "Dublin, Ireland" },
  "Europe/Paris": { lat: 48.8566, lng: 2.3522, city: "Paris, France" },
  "Europe/Berlin": { lat: 52.52, lng: 13.405, city: "Berlin, Germany" },
  "Europe/Amsterdam": { lat: 52.3676, lng: 4.9041, city: "Amsterdam, Netherlands" },
  "Europe/Madrid": { lat: 40.4168, lng: -3.7038, city: "Madrid, Spain" },
  "Europe/Rome": { lat: 41.9028, lng: 12.4964, city: "Rome, Italy" },
  "Europe/Stockholm": { lat: 59.3293, lng: 18.0686, city: "Stockholm, Sweden" },
  "Europe/Zurich": { lat: 47.3769, lng: 8.5417, city: "Zurich, Switzerland" },
  "Europe/Vienna": { lat: 48.2082, lng: 16.3738, city: "Vienna, Austria" },
  "Europe/Warsaw": { lat: 52.2297, lng: 21.0122, city: "Warsaw, Poland" },
  "Europe/Athens": { lat: 37.9838, lng: 23.7275, city: "Athens, Greece" },
  "Europe/Helsinki": { lat: 60.1699, lng: 24.9384, city: "Helsinki, Finland" },
  "Asia/Dubai": { lat: 25.2048, lng: 55.2708, city: "Dubai, UAE" },
  "Asia/Kolkata": { lat: 28.6139, lng: 77.209, city: "New Delhi, India" },
  "Asia/Bangkok": { lat: 13.7563, lng: 100.5018, city: "Bangkok, Thailand" },
  "Asia/Singapore": { lat: 1.3521, lng: 103.8198, city: "Singapore" },
  "Asia/Hong_Kong": { lat: 22.3193, lng: 114.1694, city: "Hong Kong" },
  "Asia/Shanghai": { lat: 31.2304, lng: 121.4737, city: "Shanghai, China" },
  "Asia/Tokyo": { lat: 35.6762, lng: 139.6503, city: "Tokyo, Japan" },
  "Asia/Seoul": { lat: 37.5665, lng: 126.978, city: "Seoul, South Korea" },
  "Australia/Sydney": { lat: -33.8688, lng: 151.2093, city: "Sydney, Australia" },
  "Australia/Melbourne": { lat: -37.8136, lng: 144.9631, city: "Melbourne, Australia" },
  "Pacific/Auckland": { lat: -36.8485, lng: 174.7633, city: "Auckland, New Zealand" },
};

export const PRESET_LOCATIONS = [
  { name: "San Francisco, CA, USA", lat: 37.7749, lng: -122.4194 },
  { name: "New York, NY, USA", lat: 40.7128, lng: -74.006 },
  { name: "Los Angeles, CA, USA", lat: 34.0522, lng: -118.2437 },
  { name: "Seattle, WA, USA", lat: 47.6062, lng: -122.3321 },
  { name: "Austin, TX, USA", lat: 30.2672, lng: -97.7431 },
  { name: "Chicago, IL, USA", lat: 41.8781, lng: -87.6298 },
  { name: "Boston, MA, USA", lat: 42.3601, lng: -71.0589 },
  { name: "Denver, CO, USA", lat: 39.7392, lng: -104.9903 },
  { name: "Miami, FL, USA", lat: 25.7617, lng: -80.1918 },
  { name: "Atlanta, GA, USA", lat: 33.749, lng: -84.388 },
  { name: "London, United Kingdom", lat: 51.5074, lng: -0.1278 },
  { name: "Paris, France", lat: 48.8566, lng: 2.3522 },
  { name: "Berlin, Germany", lat: 52.52, lng: 13.405 },
  { name: "Amsterdam, Netherlands", lat: 52.3676, lng: 4.9041 },
  { name: "Zurich, Switzerland", lat: 47.3769, lng: 8.5417 },
  { name: "Stockholm, Sweden", lat: 59.3293, lng: 18.0686 },
  { name: "Tokyo, Japan", lat: 35.6762, lng: 139.6503 },
  { name: "Singapore", lat: 1.3521, lng: 103.8198 },
  { name: "Sydney, Australia", lat: -33.8688, lng: 151.2093 },
  { name: "Toronto, Canada", lat: 43.6532, lng: -79.3832 },
  { name: "Vancouver, Canada", lat: 49.2827, lng: -123.1207 },
  { name: "Seoul, South Korea", lat: 37.5665, lng: 126.978 },
  { name: "Hong Kong", lat: 22.3193, lng: 114.1694 },
  { name: "Taipei, Taiwan", lat: 25.033, lng: 121.5654 },
  { name: "Bengaluru, India", lat: 12.9716, lng: 77.5946 },
  { name: "Dubai, United Arab Emirates", lat: 25.2048, lng: 55.2708 },
  { name: "Tel Aviv, Israel", lat: 32.0853, lng: 34.7818 },
  { name: "São Paulo, Brazil", lat: -23.5505, lng: -46.6333 },
];

export function getDefaultLocationFromTimezone(): { lat: number; lng: number; label: string } {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    if (tz && TIMEZONE_COORDINATES[tz]) {
      const match = TIMEZONE_COORDINATES[tz];
      return { lat: match.lat, lng: match.lng, label: match.city };
    }
  } catch {
    // ignore
  }
  return { lat: 37.7749, lng: -122.4194, label: "San Francisco, CA, USA" };
}
