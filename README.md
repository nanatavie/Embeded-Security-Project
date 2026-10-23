# Black-box power analysis attack — "The Vault"

> Project for the *Embedded Security* course — black-box attack on an Arduino Uno, built on top of the template provided by the teacher ([Embedded-Security](https://github.com/parastuffs/Embedded-Security/wiki)), using a ChipWhisperer-Nano as scope/glitcher.

## 1. Objective

The firmware running on the Arduino Uno protects a "vault" behind a password check. With no access to the source code, the goal was to:

1. physically figure out how to talk to the target,
2. bypass the password verification,
3. document the approach as an attack tree.

## 2. First contact with the target

After implementing the firmware into the Arduino Uno as instructed in the teacher GitHub, the first reflex is trying to communicated with the vault using the arduino USB connector using the standard bode rate of 115200. Unfortunately, the answer from the board was that it wasn't the main entrance.

![PuTTY COM4 — welcome message](images\not_the_main_entrance.png)

Now we know we have to access the vault using different pin than the usual RX and TX.

## 3. Finding the right PIN

With the previous information, we can now try to fin the right PIN with a logic analyzer by connecting it to the Arduino and checking which pin receive a signal when we reset the board.

![Logic analyzer capture at reset](images/logic_analyzer.png)

Once we found the TX pin (pin 11 on the Arduino), we can communicate with the board and find the RX pin. We find that it's on the Arduino pin 10 and that we have a bode rate of 9600 now.

The response we get now is the following

![Real entrance](images/Capture%20d’écran%202026-10-07%20105448.png)

## 4. Attack process

### 4.1 Board external connection

For the attack, we had to use the chipwisperer nano provided by the teacher. To connect it with the Arduino Uno we followed the instruction on [Connecting to an external target](https://github.com/parastuffs/Embedded-Security/wiki/Connecting-to-an-external-target) github of the teacher which give the base configuration of the chipwisperer and how to connect everything together. 

As seen previously the RX and TX pin of the Arduino aren't the good one to access the main entrance of the vault, we had to find which pin of the AT omega was connected to the pin 10 and 11 of the Arduino. With the multimeter, we find that its the pin 16 and 17 of the AT omega and we also found out that the trigger was on the pin 19. We can now connect those pin with the CW-Nano:

| CW-Nano | AT-Omega |
|---|---|
| 2 | GND |
| 8 | VCC (5V) |
| 10 | 17 |
| 12 | 16 |
| 16 | 19 |
| Probe B | Middle PIN measure |

### 4.2 Attack principle (SPA - Simple Power Analysis)

The method we choose to use in this project was the SPA - Simple Power Analysis. It consist in check the power consumption of the board while trying different character because the code will consume more power if the information is correct than if it's false. Using this logic, we try 10 times each possible character and take the mean and compare it to the mean value of all the character. The one that's the furthest from the mean value is suppose to be the correct character.

![Example for the first character](images/Amplitude_premier_charact.png)


## 5. Final code and result

Once we are sure that the code work we can use this method put it on loop that repeat the process and put every good answer in a list that's use to try the password at the end of every loop. If the code goes well we get the password after a few minutes and recover the salt and the hash.

```
>> ACCESS GRANTED: running protected section
Here is your salt: 49527679
Here is your hash: 05F730DB852CDFDB08140A0031093F1A65842FFA4D5092FE5495787EA02D3EF4

Enter password:
```

## 6. Attack tree

The root is the attacker goal; children are alternative approaches (OR), and the
chosen path (highlighted) decomposes into steps that must **all** succeed (AND).

```mermaid
graph TD
    G["🎯 GOAL: open the vault<br/>(recover password → salt + hash)"]

    %% --- top-level approaches (OR) ---
    G --> A["Brute-force the password<br/>over the serial link"]
    G --> B["Side-channel: Simple Power Analysis<br/>(chosen path)"]
    G --> C["Fault injection / glitching"]

    A --> A1["✗ Infeasible: unknown length,<br/>~94 printable chars per position"]
    C --> C1["✗ Not attempted"]

    %% --- chosen path: AND decomposition ---
    B --> R["1 · Establish communication<br/>(reconnaissance)"]
    B --> H["2 · Set up measurement hardware"]
    B --> S["3 · Exploit early-abort comparison"]
    B --> W["4 · ACCESS GRANTED → read salt + hash"]

    %% 1. recon
    R --> R1["Standard USB UART @115200<br/>✗ 'not the main entrance'"]
    R --> R2["Logic analyzer at reset →<br/>find hidden UART"]
    R2 --> R3["TX = Arduino pin 11<br/>RX = Arduino pin 10<br/>baud = 9600"]

    %% 2. hardware
    H --> H1["Tristate CW-Nano internal STM32<br/>(stop it perturbing measurements)"]
    H --> H2["Multimeter: map Arduino pins →<br/>ATmega 16/17, trigger on 19"]
    H --> H3["Wire CW-Nano ↔ ATmega<br/>+ power probe on VCC"]

    %% 3. SPA exploit
    S --> S1["Trigger on pin 13<br/>(stays HIGH during verification)"]
    S --> S2["Capture averaged power trace<br/>for each candidate char (×10)"]
    S --> S3["Correct char → comparison runs<br/>longer/differently → power leak"]
    S --> S4["Pick char with largest deviation<br/>at the leakage sample"]
    S --> S5["Iterate char-by-char, confirm<br/>each prefix with the oracle"]
    S5 --> S6["Password = f7-@Jp0w"]

    classDef chosen fill:#d7ebff,stroke:#1f6feb,stroke-width:2px,color:#000;
    classDef fail fill:#ffe3e3,stroke:#d32f2f,color:#000;
    classDef win fill:#dcffe0,stroke:#2e7d32,stroke-width:2px,color:#000;
    class B,R,H,S chosen;
    class A1,C1,R1 fail;
    class W,S6 win;
```

## 7. Counter-measure

Now that we know how the attack works, we can modify the firmware (`secure_sketch.ino`) to make our own SPA useless. The whole attack relies on one thing: the password check does a little more work for each character we get right. So we fix exactly that.

### 7.1 Compare in constant time (no early exit)

The original check compared the attempt character by character and stopped at the first wrong one (`early_exit_compare`). That's exactly the leak we exploited: the correct character makes the comparison run one step longer, and that shows up in the power trace.

The first measure is to always do the same amount of work, whatever we send. We never stop early and we never branch on the secret: instead we fold every difference into a single value and only look at it at the end. That way the position of the first wrong character doesn't change the power trace anymore.

### 7.2 Compare hashes instead of the plain password

To make it even stronger we don't compare the characters directly at all. We hash the attempt (with a fixed salt) and compare the resulting digest to a precomputed digest of the real password. The comparison now runs over 32 hash bytes that have nothing to do with the position of our characters, and we combine the two ideas (hash + constant time) in one function:

```cpp
bool check_password(const char *attempt) {
  uint8_t d[32];
  hashPassword(attempt, AUTH_SALT, sizeof(AUTH_SALT), d);

  // Constant time: no early exit, fold all 32 byte differences into one value.
  uint8_t diff = 0;
  for (int i = 0; i < 32; ++i) {
    diff |= (uint8_t)(d[i] ^ PASSWORD_DIGEST[i]);
  }
  return diff == 0;
}
```

The reference digest `PASSWORD_DIGEST` is computed once at boot in `setup()`, and the salt used here (`AUTH_SALT`) is kept separate from the salt/hash handed out in the protected section so we don't leak it. Now every attempt does the same amount of work (one SHA3-256) and the compare has no per-character position left to measure, so our own notebook can no longer recover the password one character at a time.
