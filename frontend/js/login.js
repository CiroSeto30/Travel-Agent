import { ApiError, getCurrentUser, login } from "./api.js";

const form = document.querySelector("#login-form");
const errorBox = document.querySelector("#form-error");
const submit = form.querySelector('button[type="submit"]');

// already logged in: go straight to the chat
getCurrentUser().then(() => location.replace("chat.html"), () => {});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.hidden = true;
  submit.setAttribute("aria-busy", "true");
  try {
    await login(form.email.value, form.password.value);
    location.assign("chat.html");
  } catch (error) {
    errorBox.textContent =
      error instanceof ApiError && error.status === 401
        ? "Email o password non corretti."
        : "Non è stato possibile accedere. Riprova tra qualche istante.";
    errorBox.hidden = false;
  } finally {
    submit.removeAttribute("aria-busy");
  }
});