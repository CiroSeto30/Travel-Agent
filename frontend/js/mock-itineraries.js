// Fake itinerary details, in the shape of GET /api/itineraries/{id} and PUT /api/itineraries/{id}/activities.
// chat.js imports these from api.js instead once the real endpoints exist (feat/planner, feat/booking).

import { ApiError } from "./api.js";

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// the proposal summaries the fake agent sends in its itinerary events
export const OPTIONS = [
  [
    { itinerary_id: 101, variant: "Economica", city: "Tokyo", origin: "NAP", destination: "HND",
      hotel: "Asakusa Hanabi Inn", hotel_stars: 3, start_date: "2027-04-10", end_date: "2027-04-16",
      travelers: 2, total: "3190.00", budget: "4000.00" },
    { itinerary_id: 102, variant: "Bilanciata", city: "Tokyo", origin: "NAP", destination: "HND",
      hotel: "Hotel Sumida Riverside", hotel_stars: 4, start_date: "2027-04-10", end_date: "2027-04-16",
      travelers: 2, total: "3770.00", budget: "4000.00" },
    { itinerary_id: 103, variant: "Comfort", city: "Osaka", origin: "NAP", destination: "KIX",
      hotel: "Osaka Castle View", hotel_stars: 5, start_date: "2027-04-10", end_date: "2027-04-16",
      travelers: 2, total: "3980.00", budget: "4000.00" },
  ],
  [
    { itinerary_id: 201, variant: "Economica", city: "Tokyo", origin: "NAP", destination: "HND",
      hotel: "Ueno Garden Hotel", hotel_stars: 3, start_date: "2027-04-17", end_date: "2027-04-23",
      travelers: 2, total: "2980.00", budget: "4000.00" },
    { itinerary_id: 202, variant: "Bilanciata", city: "Tokyo", origin: "NAP", destination: "HND",
      hotel: "Shibuya Crossing Tower", hotel_stars: 4, start_date: "2027-04-17", end_date: "2027-04-23",
      travelers: 2, total: "3640.00", budget: "4000.00" },
  ],
];

// name, start, end, price per person
const POOLS = {
  Tokyo: [
    ["Mercato di Toyosu all'alba", "05:30", "08:30", 35],
    ["Tempio Senso-ji e Asakusa", "10:00", "13:00", 20],
    ["Corso di sushi con uno chef", "11:30", "14:30", 95],
    ["Cerimonia del tè a Hamarikyu", "11:00", "12:30", 18],
    ["Museo d'arte digitale teamLab", "14:30", "17:00", 32],
    ["Onsen urbano di Odaiba", "15:00", "18:00", 30],
    ["Escursione al monte Takao", "08:30", "15:30", 25],
    ["Tour serale dei bar di Golden Gai", "20:30", "23:30", 60],
  ],
  Osaka: [
    ["Castello di Osaka", "10:00", "12:30", 15],
    ["Corso di takoyaki", "11:30", "13:30", 40],
    ["Acquario Kaiyukan", "14:00", "16:30", 28],
    ["Gita a Nara e ai cervi", "08:30", "15:00", 30],
    ["Street food a Dotonbori", "18:30", "21:00", 45],
    ["Bar di Shinsekai", "21:00", "23:30", 50],
  ],
};

const minutes = (time) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3));
const overlaps = (a, b) =>
  minutes(a.start_time) < minutes(b.end_time) + 30 && minutes(b.start_time) < minutes(a.end_time) + 30;
const money = (n) => n.toFixed(2);
const addDays = (iso, n) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

function buildDays(option) {
  const pool = POOLS[option.city];
  const nights = (new Date(option.end_date) - new Date(option.start_date)) / 86_400_000;
  const days = [];
  for (let i = 1; i < nights; i += 1) {
    // every day offers five activities of the pool, in a different order
    const offered = [...pool.slice(i % pool.length), ...pool.slice(0, i % pool.length)].slice(0, 5);
    const activities = offered.map(([name, start, end, pp], k) => ({
      activity_id: 1000 * option.itinerary_id + 10 * i + k,
      name, start_time: start, end_time: end,
      price_per_person: money(pp), price: money(pp * option.travelers), selected: false,
    }));
    // like the planner: up to two relevant activities that do not overlap
    for (const a of activities) {
      const chosen = activities.filter((x) => x.selected);
      if (chosen.length < 2 && !chosen.some((x) => overlaps(x, a))) a.selected = true;
    }
    activities.sort((a, b) => minutes(a.start_time) - minutes(b.start_time));
    days.push({ day: addDays(option.start_date, i), activities });
  }
  return days;
}

function build(option) {
  const days = buildDays(option);
  const activitiesCost = days.flatMap((d) => d.activities).filter((a) => a.selected)
    .reduce((sum, a) => sum + Number(a.price), 0);
  const fixed = Number(option.total) - activitiesCost;
  const flights = Math.round(fixed * 0.55);
  const half = Math.round(flights / 2);
  return {
    itinerary_id: option.itinerary_id, variant: option.variant, status: "proposed",
    city: option.city, travelers: option.travelers, start_date: option.start_date, end_date: option.end_date,
    budget: option.budget, total: option.total,
    flights: [
      { kind: "flight_out", origin: option.origin, destination: option.destination,
        departure_at: `${option.start_date}T10:15`, arrival_at: `${option.start_date}T23:45`,
        seats: option.travelers, price: money(half) },
      { kind: "flight_return", origin: option.destination, destination: option.origin,
        departure_at: `${option.end_date}T13:30`, arrival_at: `${addDays(option.end_date, 1)}T03:00`,
        seats: option.travelers, price: money(flights - half) },
    ],
    hotel: { name: option.hotel, stars: option.hotel_stars, nights: days.length + 1,
      rooms: [{ name: "Doppia", beds: 2, quantity: Math.ceil(option.travelers / 2) }],
      price: money(fixed - flights) },
    days,
  };
}

const store = new Map(OPTIONS.flat().map((option) => [option.itinerary_id, build(option)]));
const copy = (value) => structuredClone(value);

export function markItinerary(id, status) {
  store.get(id).status = status;
}

export const currentTotal = (id) => store.get(id).total;

export async function getItinerary(id) {
  await wait(250);
  return copy(store.get(id));
}

// selection: [{ day, activity_id }], the whole selection of the trip
export async function saveActivities(id, selection) {
  await wait(300);
  const itinerary = store.get(id);
  if (itinerary.status !== "proposed") throw new ApiError(409, { code: "not_editable" });
  const wanted = new Set(selection.map((s) => s.activity_id));
  const next = copy(itinerary);
  for (const day of next.days) {
    for (const a of day.activities) a.selected = wanted.has(a.activity_id);
    const chosen = day.activities.filter((a) => a.selected);
    if (chosen.some((a, i) => chosen.slice(i + 1).some((b) => overlaps(a, b)))) {
      throw new ApiError(422, { code: "overlap" });
    }
  }
  const fixed = next.flights.reduce((s, f) => s + Number(f.price), 0) + Number(next.hotel.price);
  const total = fixed + next.days.flatMap((d) => d.activities).filter((a) => a.selected)
    .reduce((s, a) => s + Number(a.price), 0);
  if (total > Number(next.budget)) throw new ApiError(422, { code: "over_budget" });
  next.total = money(total);
  store.set(id, next);
  return copy(next);
}