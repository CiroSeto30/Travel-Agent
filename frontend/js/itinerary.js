// Proposal tickets: used in the chat and, later, in the bookings page.

import { euro } from "./format.js";

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