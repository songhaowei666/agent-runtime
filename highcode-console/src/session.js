const USER_KEY = "highcode_user_id";
const SPACE_KEY = "highcode_space_id";

export const CODE_PATTERN = /^[A-Za-z0-9_-]+$/;

export function readSession() {
  return {
    userId: sessionStorage.getItem(USER_KEY) || "",
    spaceId: sessionStorage.getItem(SPACE_KEY) || "",
  };
}

export function saveSession(userId, spaceId) {
  sessionStorage.setItem(USER_KEY, userId);
  sessionStorage.setItem(SPACE_KEY, spaceId);
}

export function clearSession() {
  sessionStorage.removeItem(USER_KEY);
  sessionStorage.removeItem(SPACE_KEY);
}

export function hasSession() {
  const { userId, spaceId } = readSession();
  return CODE_PATTERN.test(userId) && CODE_PATTERN.test(spaceId);
}
