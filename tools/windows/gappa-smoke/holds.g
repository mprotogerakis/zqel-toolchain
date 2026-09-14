# Muss gelingen (exit 0): der Rundungsfehler einer ieee_64-Rundung auf [-1,1]
# liegt unter 2^-53. Das zwingt gappa durch seine Float- und MPFR-Pfade, nicht
# nur durch den Parser.
@rnd = float<ieee_64,ne>;
x = rnd(x_);
{ |x_| <= 1 -> |x - x_| <= 1b-53 }
