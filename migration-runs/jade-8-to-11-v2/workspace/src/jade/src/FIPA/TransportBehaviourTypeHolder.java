/*
 * File: ./FIPA/TRANSPORTBEHAVIOURTYPEHOLDER.JAVA
 * From: FIPA.IDL
 * Date: Mon Sep 04 15:08:50 2000
 *   By: idltojava Java IDL 1.2 Nov 10 1997 13:52:11
 */

package FIPA;
// JADE-FLAG:CORBA_REMOVAL file belongs to the idlj-generated FIPA IDL stub package, which exists only to carry the CORBA stubs for src/fipa.idl and is removed together with them 1.0
public final class TransportBehaviourTypeHolder
    implements org.omg.CORBA.portable.Streamable
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
{
    //	instance variable 
    public FIPA.Property[] value;
    //	constructors 
    public TransportBehaviourTypeHolder() {
	this(null);
    }
    public TransportBehaviourTypeHolder(FIPA.Property[] __arg) {
	value = __arg;
    }
    public void _write(org.omg.CORBA.portable.OutputStream out) {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
        FIPA.TransportBehaviourTypeHelper.write(out, value);
    }

    public void _read(org.omg.CORBA.portable.InputStream in) {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
        value = FIPA.TransportBehaviourTypeHelper.read(in);
    }

    public org.omg.CORBA.TypeCode _type() {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
        return FIPA.TransportBehaviourTypeHelper.type();
    }
}
