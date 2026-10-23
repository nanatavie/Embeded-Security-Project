// Minimal password prompt (Arduino) with explicit early-exit char-by-char compare
#include <Arduino.h>
#include <SoftwareSerial.h>
#include <Crypto.h>
#include <SHA3.h>

const char PASSWORD[] = "f7-@Jp0w";
//const char PASSWORD[] = "password";
const char *secret = "Je suis une petite tortue";
const int salt_size = 4;

//const uint8_t SALT[] = { 0x41, 0x42, 0x43, 0x44 };
// Buffer for digest (32 bytes for SHA3-256)
uint8_t digest[32];

// --- Fix 2: fixed salt + precomputed digest used ONLY for authentication.
// Kept separate from the salt/hash handed out in the protected section.
const uint8_t AUTH_SALT[4] = { 0x11, 0x22, 0x33, 0x44 };
uint8_t PASSWORD_DIGEST[32];   // = SHA3-256(AUTH_SALT || PASSWORD), computed in setup()

// choose pins: RX is the pin Arduino listens on (connect TX of other device here)
// TX is the pin Arduino transmits on (connect RX of other device here)
const uint8_t MY_RX_PIN = 10;
const uint8_t MY_TX_PIN = 11;

SoftwareSerial comms(MY_RX_PIN, MY_TX_PIN); // RX, TX

void setup() {
  Serial.begin(115200);
  while (!Serial) { delay(10); }
  Serial.println();
  Serial.println("Welcome to the vault. This is not the main entrance.");
  comms.begin(9600);          // software serial communications

  // Fix 2: precompute the reference digest once, at boot.
  hashPassword(PASSWORD, AUTH_SALT, sizeof(AUTH_SALT), PASSWORD_DIGEST);

  comms.println("Enter password:");

  pinMode(13, OUTPUT);
  digitalWrite(13, LOW);
}

void hashPassword(const char *password, const uint8_t *salt, size_t saltLen, uint8_t *outDigest) {
  SHA3_256 sha3;
  sha3.reset();

  // Add salt
  sha3.update(salt, saltLen);

  // Add password
  sha3.update((const uint8_t *)password, strlen(password));

  // Finalize
  sha3.finalize(outDigest, 32);
}

String readLine(Stream &s) {
  String str;
  while (true) {
    if (s.available()) {
      char c = s.read();
      if (c == '\r' or c == '\n') break;
      str += c;
    }
  }
  return str;
}

// Fix 2: hash the attempt (salted) and compare DIGESTS, using
// Fix 1: a constant-time compare (no early exit).
// The compare runs over hash bytes that are uncorrelated with the attempt
// characters, so there is no per-character position left for SPA to exploit,
// and the SHA3 work is the same for every attempt.
bool check_password(const char *attempt) {
  uint8_t d[32];
  hashPassword(attempt, AUTH_SALT, sizeof(AUTH_SALT), d); // reuse the same routine

  // Fix 1 (constant time): no early exit, fold all 32 byte differences into one value.
  uint8_t diff = 0;
  for (int i = 0; i < 32; ++i) {
    diff |= (uint8_t)(d[i] ^ PASSWORD_DIGEST[i]);
  }
  return diff == 0;
}

void protected_section(Stream &out) {
  out.println(">> ACCESS GRANTED: running protected section");

  uint8_t SALT[4];
  for (int i = 0; i < salt_size; i++) {
    SALT[i] = (uint8_t) random(0x21, 0x7E);
  }

  hashPassword(secret, SALT, sizeof(SALT), digest);

  out.print("Here is your salt: ");
  for (int i = 0; i < 4; i++) {
    if (SALT[i] < 0x10) out.print("0");
    out.print(SALT[i], HEX);
  }
  out.println();
  out.print("Here is your hash: ");
  for (int i = 0; i < 32; i++) {
    if (digest[i] < 0x10) out.print("0");
    out.print(digest[i], HEX);
  }
  out.println();
}

void loop() {
  if (comms.available()) {
    String attempt = readLine(comms);
    attempt.trim();
    if (attempt.length() == 0) {
      comms.println("No input. Enter password:");
      return;
    }

    char attempt_c[64];
    attempt.toCharArray(attempt_c, sizeof(attempt_c));

    digitalWrite(13, HIGH);
    if (check_password(attempt_c)) {
      protected_section(comms);
    } else {
      comms.println(">> ACCESS DENIED");
    }
    digitalWrite(13, LOW);

    comms.println();
    comms.println("Enter password:");
  }
}
