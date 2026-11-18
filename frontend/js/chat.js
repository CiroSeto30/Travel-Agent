import { dateRange, euro, monthName } from "./format.js";
import { ApiError, createConversation, getDestinations, getItinerary, saveActivities, sendMessage } from "./api.js";
import {
  createTicket, renderDetails, selectTicket, selectionOf, setTicketTotal, stampTicket, supersedeTicket, toggleActivity,
} from "./itinerary.js";
import { requireUser } from "./session.js";

let conversationId = null; // created with the first message, so an unused page leaves no empty conversation

async function* replyTo(text) {
  conversationId ??= (await createConversation()).id;
  yield* sendMessage(conversationId, text);
}

function welcome(user, destinations) {
  const countries = destinations.countries.map((c) => c.country);
  const list = countries.length > 1 ? `${countries.slice(0, -1).join(", ")} e ${countries.at(-1)}` : countries[0];
  const departures = destinations.departures.map((d) => d.city).join(", ");
  return (
    `Ciao ${user.first_name}! Posso organizzare viaggi in ${list}, con partenza da ${departures}. ` +
    "Dimmi dove vorresti andare, in che mese, per quante notti, in quanti siete, con che budget e da dove parti."
  );
}

const layout = document.querySelector(".chat-layout");
const messages = document.querySelector("#messages");
const requirementsBar = document.querySelector("#requirements");
const form = document.querySelector("#composer");
const input = form.message;
const details = document.querySelector("#details");
const ticketsById = new Map();
const ticketsBySet = new Map();
const note = details.querySelector(".details__note");
let busy = false;
let opened = null; // { itinerary, saved, ticket, view, version } for the itinerary in the panel

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
  for (const ticket of ticketsBySet.get(data.supersedes) ?? []) {
    supersedeTicket(ticket);
    if (opened?.ticket === ticket) makeReadOnly("superseded");
  }

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
  if (!ticket) return;
  stampTicket(ticket);
  if (opened?.ticket === ticket) makeReadOnly("booked");
  // the other proposals of the same answer can no longer be booked
  const siblings = [...ticketsBySet.values()].find((tickets) => tickets.includes(ticket)) ?? [];
  for (const other of siblings.filter((t) => t !== ticket)) {
    supersedeTicket(other);
    if (opened?.ticket === other) makeReadOnly("superseded");
  }
}

function showNote(text, isError = false) {
  note.textContent = text ?? "";
  note.hidden = !text;
  note.classList.toggle("is-error", isError);
}

function showTotal(itinerary) {
  details.querySelector(".details__total").textContent = euro(itinerary.total);
}

function render() {
  const editable = opened.itinerary.status === "proposed";
  opened.view = renderDetails(details.querySelector(".details__program"), opened.itinerary, {
    editable,
    onToggle: changeActivity,
  });
  details.querySelector(".details__book").hidden = !editable;
  showTotal(opened.itinerary);
}

function makeReadOnly(status) {
  opened.itinerary.status = status;
  opened.saved.status = status;
  showNote(null);
  render();
}

async function openDetails(option, ticket) {
  selectTicket(ticket);
  details.querySelector(".details__variant").textContent = option.variant;
  details.querySelector(".details__trip").textContent =
    `${option.city}, ${dateRange(option.start_date, option.end_date)}, ` +
    `${option.travelers === 1 ? "1 persona" : `${option.travelers} persone`}`;
  details.querySelector(".details__program").replaceChildren();
  details.querySelector(".details__book").dataset.variant = option.variant;
  details.querySelector(".details__book").hidden = true;
  showTotal(option);
  showNote("Carico il programma…");
  details.hidden = false;
  layout.classList.add("has-details");
  details.querySelector(".details__close").focus();

  try {
    const itinerary = await getItinerary(option.itinerary_id);
    if (!ticket.classList.contains("is-selected")) return; // another ticket was opened meanwhile
    opened = { itinerary, saved: itinerary, ticket, view: null, version: 0 };
    showNote(null);
    render();
  } catch {
    showNote("Non è stato possibile caricare il programma. Chiudi e riapri i dettagli.", true);
  }
}

function changeActivity(activityId, checked) {
  const result = toggleActivity(opened.itinerary, activityId, checked);
  if (result.overBudget) {
    opened.view.update(opened.itinerary); // put the checkbox back
    showNote(`Con "${result.target.name}" si supera il budget. Togli un'altra attività o alza il budget in chat.`, true);
    return;
  }
  opened.itinerary = result.itinerary;
  opened.view.update(result.itinerary);
  showTotal(result.itinerary);
  showNote(result.removed.length
    ? `Tolto "${result.removed.map((a) => a.name).join('", "')}": si sovrapponeva a "${result.target.name}".`
    : null);
  save(opened);
}

function saveErrorMessage(error) {
  const code = error instanceof ApiError ? error.detail?.code : null;
  if (code === "over_budget") return "Con questa scelta si supera il budget. Togli un'attività o alza il budget in chat.";
  if (code === "overlap") return "Due attività si sovrappongono: scegline una sola.";
  if (code === "not_editable") return "Questa proposta non si può più modificare.";
  if (code === "unavailable") return "Un'attività si è appena esaurita. Scegline un'altra.";
  return "Non è stato possibile salvare la modifica. Riprova.";
}

// Every change saves the whole selection; only the answer to the latest change is applied.
async function save(state) {
  const version = ++state.version;
  try {
    const saved = await saveActivities(state.itinerary.itinerary_id, selectionOf(state.itinerary));
    if (version !== state.version) return;
    state.saved = saved;
    state.itinerary = saved;
    setTicketTotal(state.ticket, saved.total);
    if (opened === state) {
      state.view.update(saved);
      showTotal(saved);
    }
  } catch (error) {
    if (version !== state.version) return;
    state.itinerary = state.saved;
    if (opened === state) {
      state.view.update(state.saved);
      showTotal(state.saved);
      showNote(saveErrorMessage(error), true);
    }
  }
}

function closeDetails() {
  details.hidden = true;
  layout.classList.remove("has-details");
  opened = null;
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
  } catch (error) {
    reply.status(null);
    reply.error(error instanceof ApiError && error.status === 401
      ? "La sessione è scaduta: accedi di nuovo."
      : "La risposta si è interrotta. Invia di nuovo il messaggio.");
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
addAssistantMessage().write(welcome(user, await getDestinations()));
input.focus();
