/*
 * File: ./FIPA/TRANSPORTBEHAVIOURTYPEHELPER.JAVA
 * From: FIPA.IDL
 * Date: Mon Sep 04 15:08:50 2000
 *   By: idltojava Java IDL 1.2 Nov 10 1997 13:52:11
 */

package FIPA;
// JADE-FLAG:CORBA_REMOVAL file belongs to the idlj-generated FIPA IDL stub package, which exists only to carry the CORBA stubs for src/fipa.idl and is removed together with them 1.0
public class TransportBehaviourTypeHelper {
     // It is useless to have instances of this class
     private TransportBehaviourTypeHelper() { }

    public static void write(org.omg.CORBA.portable.OutputStream out, FIPA.Property[] that)  {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
          {
              out.write_long(that.length);
              for (int __index = 0 ; __index < that.length ; __index += 1) {
                  FIPA.PropertyHelper.write(out, that[__index]);
              }
          }
    }
    public static FIPA.Property[] read(org.omg.CORBA.portable.InputStream in) {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
          FIPA.Property[] that;
          {
              int __length = in.read_long();
              that = new FIPA.Property[__length];
              for (int __index = 0 ; __index < that.length ; __index += 1) {
                  that[__index] = FIPA.PropertyHelper.read(in);
              }
          }
          return that;
    }
   public static FIPA.Property[] extract(org.omg.CORBA.Any a) {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
     org.omg.CORBA.portable.InputStream in = a.create_input_stream();
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
     return read(in);
   }
   public static void insert(org.omg.CORBA.Any a, FIPA.Property[] that) {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
     org.omg.CORBA.portable.OutputStream out = a.create_output_stream();
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
     a.type(type());
     write(out, that);
     a.read_value(out.create_input_stream(), type());
   }
   private static org.omg.CORBA.TypeCode _tc;
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
   synchronized public static org.omg.CORBA.TypeCode type() {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
          if (_tc == null)
             _tc = org.omg.CORBA.ORB.init().create_alias_tc(id(), "TransportBehaviourType", org.omg.CORBA.ORB.init().create_sequence_tc(0, FIPA.PropertyHelper.type()));
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
      return _tc;
   }
   public static String id() {
       return "IDL:FIPA/TransportBehaviourType:1.0";
   }
}
