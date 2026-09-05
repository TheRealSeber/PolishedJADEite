/*
 * File: ./FIPA/PROPERTYHELPER.JAVA
 * From: FIPA.IDL
 * Date: Mon Sep 04 15:08:50 2000
 *   By: idltojava Java IDL 1.2 Nov 10 1997 13:52:11
 */

package FIPA;
// JADE-FLAG:CORBA_REMOVAL file belongs to the idlj-generated FIPA IDL stub package, which exists only to carry the CORBA stubs for src/fipa.idl and is removed together with them 1.0
public class PropertyHelper {
     // It is useless to have instances of this class
     private PropertyHelper() { }

    public static void write(org.omg.CORBA.portable.OutputStream out, FIPA.Property that) {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
	out.write_string(that.keyword);
	out.write_any(that.value);
    }
    public static FIPA.Property read(org.omg.CORBA.portable.InputStream in) {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
        FIPA.Property that = new FIPA.Property();
	that.keyword = in.read_string();
	that.value = in.read_any();
        return that;
    }
   public static FIPA.Property extract(org.omg.CORBA.Any a) {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
     org.omg.CORBA.portable.InputStream in = a.create_input_stream();
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
     return read(in);
   }
   public static void insert(org.omg.CORBA.Any a, FIPA.Property that) {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
     org.omg.CORBA.portable.OutputStream out = a.create_output_stream();
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
     write(out, that);
     a.read_value(out.create_input_stream(), type());
   }
   private static org.omg.CORBA.TypeCode _tc;
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
   synchronized public static org.omg.CORBA.TypeCode type() {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
       int _memberCount = 2;
       org.omg.CORBA.StructMember[] _members = null;
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
          if (_tc == null) {
               _members= new org.omg.CORBA.StructMember[2];
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
               _members[0] = new org.omg.CORBA.StructMember(
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
                 "keyword",
                 org.omg.CORBA.ORB.init().get_primitive_tc(org.omg.CORBA.TCKind.tk_string),
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
                 null);

               _members[1] = new org.omg.CORBA.StructMember(
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
                 "value",
                 org.omg.CORBA.ORB.init().get_primitive_tc(org.omg.CORBA.TCKind.tk_any),
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
                 null);
             _tc = org.omg.CORBA.ORB.init().create_struct_tc(id(), "Property", _members);
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
          }
      return _tc;
   }
   public static String id() {
       return "IDL:FIPA/Property:1.0";
   }
}
