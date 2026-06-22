Handwriting Recognizer — portable, no install required
=======================================================

This is a single self-contained program. There is nothing to install: no
Python, no internet, no AI service. It runs entirely on this machine.

WHAT'S HERE
  handwriting.exe   the whole program (the trained model is built in)

HOW TO RUN (Windows)
  1. Copy handwriting.exe somewhere on the PC (or run it straight from the USB
     stick).
  2. Open a Command Prompt in that folder
     (Shift + right-click the folder -> "Open command window / PowerShell here").
  3. Read a scanned line of handwriting:

         handwriting.exe read -image C:\path\to\line.png

     Recognize a single character:

         handwriting.exe predict -image C:\path\to\letter.png

  Supported images: PNG and JPEG.

TIPS
  - For best results, scan or photograph the writing fairly straight, dark ink
    on light paper. The program crops and centers each character automatically.
  - Add -v to "read" to see the confidence for every character:
         handwriting.exe read -image line.png -v
  - Add -minconf 0.6 to flag low-confidence characters with a dot, so a person
    can double-check them.

That's it. Delete the file to uninstall — it leaves nothing behind.
