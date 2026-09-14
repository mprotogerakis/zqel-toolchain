# Muss scheitern (exit 1) UND die erreichte Schranke nennen. Ein Prueftest, der
# nur das Gelingen prueft, kann ein gappa nicht von einem Programm
# unterscheiden, das immer 0 zurueckgibt.
@rnd = float<ieee_64,ne>;
x = rnd(x_);
{ |x_| <= 1 -> |x - x_| <= 1b-60 }
