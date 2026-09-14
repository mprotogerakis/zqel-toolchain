(* Rauchprobe fuer iec2c: klein, aber sie zwingt den Uebersetzer durch alle
   vier Stufen - Parser, Semantik, Typaufloesung und C-Erzeugung. Ein reiner
   Parsertest wuerde ein iec2c nicht von einem Programm unterscheiden, das
   `exit 0` sagt. Deshalb prueft das Bauskript die ERZEUGTEN Dateien.

   Die Variable heisst ceiling und nicht limit: LIMIT(MN,IN,MX) ist eine
   Standardfunktion der IEC 61131-3 und damit reserviert. Der erste Entwurf
   stolperte darueber - ein Beleg, dass diese Probe die Semantikstufe wirklich
   erreicht und nicht im Parser stehenbleibt. *)
PROGRAM prog0
  VAR
    count : INT := 0;
    ceiling : INT := 10;
    full  : BOOL;
  END_VAR
  count := count + 1;
  full  := count >= ceiling;
  IF full THEN
    count := 0;
  END_IF;
END_PROGRAM

CONFIGURATION Config0
  RESOURCE Res0 ON PLC
    TASK task0(INTERVAL := T#20ms, PRIORITY := 0);
    PROGRAM inst0 WITH task0 : prog0;
  END_RESOURCE
END_CONFIGURATION
