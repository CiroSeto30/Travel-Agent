// The logged-in user on protected pages: redirect to the login page if there is none.

import { ApiError, getCurrentUser, logout } from "./api.js";

export async function requireUser() {
  try {
    const user = await getCurrentUser();
    showUser(user);
    return user;
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) location.replace("index.html");
    throw error;
  }
}

function showUser(user) {
  const name = document.querySelector(".user-name");
  if (name) name.textContent = user.first_name;
  document.querySelector("#logout")?.addEventListener("click", async () => {
    await logout();
    location.replace("index.html");
  });
}