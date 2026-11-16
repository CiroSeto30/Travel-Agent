import { dateRange, euro, monthName } from "./format.js";
import { createTicket, selectTicket, stampTicket, supersedeTicket } from "./itinerary.js";
import { mockReply, welcome } from "./mock.js";
import { requireUser } from "./session.js";

// until the agent endpoint exists (feat/agent), replies come from the fake agent
const replyTo = mockReply;

const layout = document.querySelector(".chat-layout");
const messages = document.querySelector("#messages");
const requirementsBar = document.querySelector("#requirements");
const form = document.querySelector("#composer");
const input = form.message;
const details = document.querySelector("#details");
const ticketsById = new Map();
const ticketsBySet = new Map();
let busy = false;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function scrollToEnd() {
  messages.scrollTop = messages.scrollHeight;
}

function addUserMessage(text) {
  messages.append(element("div", "message message--user", text));
  scrollToEnd();
}

// An assistant message is built while the events arrive: text, then tickets, then more text.
function addAssistantMessage() {
  const node = element("div", "message message--assistant");
  const status = element("p", "message__status");
  status.hidden = true;
  node.append(status);
  messages.append(node);

  let paragraph = null;
  return {
    write(text) {
      if (!paragraph) {
        paragraph = element("p", "message__text");
        node.append(paragraph);
      }
      paragraph.textContent += text;
      scrollToEnd();
    },
    status(label) {
      status.textContent = label ?? "";
      status.hidden = !label;
    },
    tickets(list) {
      node.append(list);
      paragraph = null; // text after the tickets starts a new paragraph
      scrollToEnd();
    },
    error(text) {
      node.append(element("p", "message__error", text));
    },
  };
}

function showRequirements(r) {
  const parts = [
    r.country,
    r.month && monthName(r.month),
    r.nights && `${r.nights} notti`,
    r.travelers && (r.travelers === 1 ? "1 persona" : `${r.travelers} persone`),
    r.budget && `budget ${euro(r.budget)}`,
    r.origin && `partenza da ${r.origin}`,
  ].filter(Boolean);
  requirementsBar.textContent = parts.join(", ");
  requirementsBar.hidden = parts.length === 0;
}

function showProposals(data, reply) {
  for (const ticket of ticketsBySet.get(data.supersedes) ?? []) supersedeTicket(ticket);

  const list = element("ul", "tickets");
  const tickets = data.options.map((option) => {
    const ticket = createTicket(option, openDetails);
    ticketsById.set(option.itinerary_id, ticket);
    return ticket;
  });
  ticketsBySet.set(data.proposal_set_id, tickets);
  list.append(...tickets);
  reply.tickets(list);
}

function showBooking(data) {
  const ticket = ticketsById.get(data.itinerary_id);
  stampTicket(ticket);
  if (ticket.classList.contains("is-selected")) details.querySelector(".details__book").hidden = true;
}

function openDetails(option, ticket) {
  selectTicket(ticket);
  details.querySelector(".details__variant").textContent = option.variant;
  details.querySelector(".details__total").textContent = euro(option.total);
  details.querySelector(".details__trip").textContent =
    `${option.city}, ${dateRange(option.start_date, option.end_date)}, ` +
    `${option.travelers === 1 ? "1 persona" : `${option.travelers} persone`}`;
  details.querySelector(".details__book").dataset.variant = option.variant;
  details.querySelector(".details__book").hidden =
    ticket.classList.contains("is-superseded") || ticket.classList.contains("is-booked");
  details.hidden = false;
  layout.classList.add("has-details");
  details.querySelector(".details__close").focus();
}

function closeDetails() {
  details.hidden = true;
  layout.classList.remove("has-details");
  const selected = document.querySelector(".ticket.is-selected .ticket__open");
  selectTicket(null);
  selected?.focus();
}

async function send(text) {
  if (busy || !text) return;
  busy = true;
  form.setAttribute("aria-busy", "true");
  addUserMessage(text);
  const reply = addAssistantMessage();
  try {
    for await (const { event, data } of replyTo(text)) {
      if (event === "requirements") showRequirements(data);
      else if (event === "tool_start") reply.status(`${data.label}…`);
      else if (event === "tool_end") reply.status(null);
      else if (event === "token") reply.write(data.text);
      else if (event === "itinerary") showProposals(data, reply);
      else if (event === "booking") showBooking(data);
      else if (event === "error") reply.error(data.message);
    }
  } catch {
    reply.status(null);
    reply.error("La risposta si è interrotta. Invia di nuovo il messaggio.");
  } finally {
    busy = false;
    form.removeAttribute("aria-busy");
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = input.value.trim();
  input.value = "";
  send(text);
});

// Enter sends, Shift+Enter starts a new line
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

details.querySelector(".details__close").addEventListener("click", closeDetails);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !details.hidden) closeDetails();
});
details.querySelector(".details__book").addEventListener("click", (event) => {
  send(`Prenota l'opzione ${event.currentTarget.dataset.variant.toLowerCase()}`);
});

const user = await requireUser();
addAssistantMessage().write(welcome(user));
input.focus();