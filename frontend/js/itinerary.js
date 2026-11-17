// Proposal tickets and the details panel: used in the chat and, later, in the bookings page.

import { clock, euro, longDay, shortDay } from "./format.js";

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function createTicket(option, onOpen) {
  const ticket = element("li", "ticket");
  ticket.dataset.itineraryId = option.itinerary_id;

  const route = element("span", "ticket__route");
  route.setAttribute("aria-label", `Da ${option.origin} a ${option.destination}`);
  route.append(option.origin, element("span", "ticket__arrow", "→"), option.destination);

  const body = element("span", "ticket__body");
  const meta = element("span", "ticket__meta", `${option.city}, ${option.hotel}, ${option.hotel_stars} stelle`);
  meta.dataset.text = meta.textContent;
  body.append(element("strong", "ticket__variant", option.variant), meta);

  const open = element("button", "ticket__open", "Dettagli");
  open.type = "button";
  open.addEventListener("click", () => onOpen(option, ticket));

  ticket.append(route, body, element("span", "ticket__price", euro(option.total)), open);
  return ticket;
}

function setMeta(ticket, text) {
  const meta = ticket.querySelector(".ticket__meta");
  meta.textContent = text ?? meta.dataset.text;
}

export function selectTicket(ticket) {
  for (const other of document.querySelectorAll(".ticket.is-selected")) {
    other.classList.remove("is-selected");
    if (!other.classList.contains("is-superseded")) setMeta(other);
  }
  if (!ticket) return;
  ticket.classList.add("is-selected");
  if (!ticket.classList.contains("is-superseded")) setMeta(ticket, "Aperta nei dettagli");
}

export function supersedeTicket(ticket) {
  ticket.classList.add("is-superseded");
  setMeta(ticket, "Sostituita da una proposta più recente");
}

export function stampTicket(ticket) {
  ticket.classList.add("is-booked");
  ticket.querySelector(".ticket__price").before(element("span", "stamp", "Prenotato"));
}

export function setTicketTotal(ticket, total) {
  ticket.querySelector(".ticket__price").textContent = euro(total);
}

// Activity choice. The page applies the rules to answer at once; the server checks them again on save.

const minutes = (time) => Number(time.slice(0, 2)) * 60 + Number(time.slice(3));
const GAP = 30; // minutes needed between two activities of the same day

export const overlaps = (a, b) =>
  minutes(a.start_time) < minutes(b.end_time) + GAP && minutes(b.start_time) < minutes(a.end_time) + GAP;

const sum = (values) => values.reduce((total, value) => total + Number(value), 0);

function totalOf(itinerary) {
  const fixed = sum(itinerary.flights.map((f) => f.price)) + Number(itinerary.hotel.price);
  const activities = itinerary.days.flatMap((d) => d.activities).filter((a) => a.selected);
  return (fixed + sum(activities.map((a) => a.price))).toFixed(2);
}

// Check or uncheck one activity: overlapping activities of that day are unchecked.
export function toggleActivity(itinerary, activityId, checked) {
  const next = structuredClone(itinerary);
  const day = next.days.find((d) => d.activities.some((a) => a.activity_id === activityId));
  const target = day.activities.find((a) => a.activity_id === activityId);
  target.selected = checked;
  const removed = checked ? day.activities.filter((a) => a !== target && a.selected && overlaps(a, target)) : [];
  for (const activity of removed) activity.selected = false;
  next.total = totalOf(next);
  return { itinerary: next, removed, target, overBudget: Number(next.total) > Number(next.budget) };
}

export const selectionOf = (itinerary) =>
  itinerary.days.flatMap((d) => d.activities.filter((a) => a.selected).map((a) => ({ day: d.day, activity_id: a.activity_id })));

// Details panel: budget, flights, hotel and the program day by day.
// Returns update(itinerary), which syncs checkboxes and budget without rebuilding (keyboard focus stays put).

function budgetText(itinerary) {
  const total = Number(itinerary.total);
  const budget = Number(itinerary.budget);
  return total > budget
    ? `${euro(total)} di ${euro(budget)}, oltre il budget di ${euro(total - budget)}.`
    : `${euro(total)} di ${euro(budget)}, restano ${euro(budget - total)}.`;
}

function section(title) {
  const node = element("section", "details__section");
  node.append(element("h3", "details__section-title", title));
  return node;
}

function flightRow(flight) {
  const row = element("div", "flight");
  const route = element("span", "flight__route");
  route.setAttribute("aria-label", `Da ${flight.origin} a ${flight.destination}`);
  route.append(flight.origin, element("span", "ticket__arrow", "→"), flight.destination);
  const nextDay = flight.arrival_at.slice(0, 10) !== flight.departure_at.slice(0, 10) ? " (+1)" : "";
  const when = element("span", "flight__when",
    `${shortDay(flight.departure_at.slice(0, 10))}, ${clock(flight.departure_at)}–${clock(flight.arrival_at)}${nextDay}`);
  const seats = flight.seats === 1 ? "1 posto" : `${flight.seats} posti`;
  row.append(route, when, element("span", "flight__price", `${seats}, ${euro(flight.price)}`));
  return row;
}

function activityRow(activity, editable, onToggle) {
  const row = element(editable ? "label" : "div", "activity");
  if (editable) {
    const box = element("input");
    box.type = "checkbox";
    box.checked = activity.selected;
    box.dataset.id = activity.activity_id;
    box.addEventListener("change", () => onToggle(activity.activity_id, box.checked));
    row.append(box);
  }
  const name = element("span", "activity__name", activity.name);
  name.append(element("span", "activity__per-person", `${euro(activity.price_per_person)} a persona`));
  row.append(
    element("span", "activity__time", `${activity.start_time}–${activity.end_time}`),
    name,
    element("span", "activity__price", euro(activity.price)),
  );
  return row;
}

export function renderDetails(container, itinerary, { editable, onToggle }) {
  container.replaceChildren();

  const budget = element("div", "budget");
  const bar = element("div", "budget__bar");
  const fill = element("div", "budget__fill");
  bar.append(fill);
  const text = element("p", "budget__text");
  budget.append(bar, text);

  const flights = section("Voli");
  flights.append(...itinerary.flights.map(flightRow));

  const hotel = section("Hotel");
  const rooms = itinerary.hotel.rooms.map((r) => `${r.quantity} ${r.name.toLowerCase()}`).join(", ");
  const hotelRow = element("div", "hotel");
  hotelRow.append(
    element("span", "hotel__name", `${itinerary.hotel.name}, ${itinerary.hotel.stars} stelle`),
    element("span", "hotel__rooms", `${rooms}, ${itinerary.hotel.nights} notti`),
    element("span", "hotel__price", euro(itinerary.hotel.price)),
  );
  hotel.append(hotelRow);

  const program = section("Programma");
  if (editable) {
    program.append(element("p", "details__hint",
      "Spunta le attività che vuoi fare. Due attività che si sovrappongono non si possono scegliere insieme."));
  }
  for (const day of itinerary.days) {
    const shown = editable ? day.activities : day.activities.filter((a) => a.selected);
    const group = element("div", "day");
    group.append(element("h4", "day__title", longDay(day.day)));
    if (shown.length === 0) group.append(element("p", "day__empty", "Giornata libera."));
    group.append(...shown.map((a) => activityRow(a, editable, onToggle)));
    program.append(group);
  }

  container.append(budget, flights, hotel, program);

  function update(next) {
    const total = Number(next.total);
    const limit = Number(next.budget);
    fill.style.width = `${Math.min(100, Math.round((total / limit) * 100))}%`;
    budget.classList.toggle("is-over", total > limit);
    text.textContent = budgetText(next);
    const selected = new Set(next.days.flatMap((d) => d.activities).filter((a) => a.selected).map((a) => a.activity_id));
    for (const box of container.querySelectorAll('input[type="checkbox"]')) box.checked = selected.has(Number(box.dataset.id));
  }
  update(itinerary);
  return { update };
}