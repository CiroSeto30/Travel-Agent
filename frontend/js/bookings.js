// The bookings page: every confirmed trip as a stamped ticket; "Dettagli" opens the program, read only.

import { getBookings, getItinerary } from "./api.js";
import { dateRange, euro } from "./format.js";
import { createTicket, renderDetails, selectTicket, stampTicket } from "./itinerary.js";
import { requireUser } from "./session.js";

const layout = document.querySelector(".chat-layout");
const list = document.querySelector("#bookings");
const status = document.querySelector("#bookings-status");
const details = document.querySelector("#details");
const note = details.querySelector(".details__note");

function showNote(text, isError = false) {
  note.textContent = text ?? "";
  note.hidden = !text;
  note.classList.toggle("is-error", isError);
}

async function openDetails(option, ticket) {
  selectTicket(ticket);
  details.querySelector(".details__variant").textContent = option.variant;
  details.querySelector(".details__trip").textContent =
    `${option.city}, ${dateRange(option.start_date, option.end_date)}, ` +
    `${option.travelers === 1 ? "1 persona" : `${option.travelers} persone`}`;
  details.querySelector(".details__total").textContent = euro(option.total);
  details.querySelector(".details__program").replaceChildren();
  showNote("Carico il programma…");
  details.hidden = false;
  layout.classList.add("has-details");
  details.querySelector(".details__close").focus();
  try {
    const itinerary = await getItinerary(option.itinerary_id);
    if (!ticket.classList.contains("is-selected")) return; // another ticket was opened meanwhile
    showNote(null);
    renderDetails(details.querySelector(".details__program"), itinerary, { editable: false, onToggle: () => {} });
  } catch {
    showNote("Non è stato possibile caricare il programma. Chiudi e riapri i dettagli.", true);
  }
}

function closeDetails() {
  details.hidden = true;
  layout.classList.remove("has-details");
  const selected = document.querySelector(".ticket.is-selected .ticket__open");
  selectTicket(null);
  selected?.focus();
}

details.querySelector(".details__close").addEventListener("click", closeDetails);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !details.hidden) closeDetails();
});

await requireUser();
try {
  const bookings = await getBookings();
  status.textContent = bookings.length
    ? ""
    : "Non hai ancora prenotazioni. Organizza un viaggio in chat e confermalo: lo troverai qui.";
  status.hidden = bookings.length > 0;
  for (const booking of bookings) {
    const ticket = createTicket(booking.itinerary, openDetails);
    stampTicket(ticket);
    list.append(ticket);
  }
} catch {
  status.textContent = "Non è stato possibile caricare le prenotazioni. Ricarica la pagina.";
  status.classList.add("is-error");
}
