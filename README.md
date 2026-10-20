# Black-box power analysis attack — "The Vault"

> Project for the *Embedded Security* course — black-box attack on an Arduino Uno, built on top of the template provided by the teacher ([Embedded-Security](https://github.com/parastuffs/Embedded-Security/wiki)), using a ChipWhisperer-Nano as scope/glitcher.

## 1. Objective

The firmware running on the Arduino Uno protects a "vault" behind a password check. With no access to the source code, the goal was to:

1. physically figure out how to talk to the target,
2. bypass the password verification,
3. document the approach as an attack tree.

## 2. First contact with the target

After implementing the firmware into the Arduino Uno as instructed in the teacher GitHub, the first reflex is trying to communicated with the vault using the arduino USB connector using the standart bode rate of 115200. Unfortunatly, the awnser from the board was that it wasn't the main entrance.

![PuTTY COM4 — welcome message](images\not_the_main_entrance.png)

Now we know we have to acces the vault using different pin than the usual RX and TX.

## 3. Finding the right PIN

With the previous information, we can now try to fin the right PIN with a logic analyzer by connecting it to the Arduino and checking which pin recieve a signal when we reset the board.

![Logic analyzer capture at reset](images/logic_analyzer.png)

Once we found the TX pin (pin 11 on the Arduino), we can communicate with the board and find the RX pin. We find that it's on the Arduino pin 10 and that we have a bode rate of 9600 now.

The reponse we get now is the following

![Real entrance](images/Capture%20d’écran%202026-10-07%20105448.png)

## 4. Attack process

### 4.1 