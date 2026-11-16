import { ApiError, getAirports, register } from "./api.js";

const form = document.querySelector("#register-form");
const errorBox = document.querySelector("#form-error");
const submit = form.querySelector('button[type="submit"]');

async function loadAirports() {
  const airports = await getAirports();
  form.home_airport.append(
    ...airports.map((a) => new Option(`${a.city} (${a.iata})`, a.iata)),
  );
}

function messageFor(error) {
  if (!(error instanceof ApiError)) return "Non è stato possibile registrarsi. Riprova tra qualche istante.";
  if (error.status === 409) return "Esiste già un account con questa email. Accedi invece di registrarti.";
  if (error.status === 422) return "Controlla i dati: la password deve avere almeno 8 caratteri.";
  return "Non è stato possibile registrarsi. Riprova tra qualche istante.";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.hidden = true;
  submit.setAttribute("aria-busy", "true");
  try {
    await register(Object.fromEntries(new FormData(form)));
    location.assign("chat.html");
  } catch (error) {
    errorBox.textContent = messageFor(error);
    errorBox.hidden = false;
  } finally {
    submit.removeAttribute("aria-busy");
  }
});

loadAirports().catch(() => {
  errorBox.textContent = "Non è stato possibile caricare gli aeroporti. Ricarica la pagina.";
  errorBox.hidden = false;
});