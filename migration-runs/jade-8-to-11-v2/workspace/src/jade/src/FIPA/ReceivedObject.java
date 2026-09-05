/*
 * File: ./FIPA/RECEIVEDOBJECT.JAVA
 * From: FIPA.IDL
 * Date: Mon Sep 04 15:08:50 2000
 *   By: idltojava Java IDL 1.2 Nov 10 1997 13:52:11
 */

package FIPA;
// JADE-FLAG:CORBA_REMOVAL file belongs to the idlj-generated FIPA IDL stub package, which exists only to carry the CORBA stubs for src/fipa.idl and is removed together with them 1.0
public final class ReceivedObject {
    //	instance variables
    public String by;
    public String from;
    public FIPA.DateTime date;
    public String id;
    public String via;
    //	constructors
    public ReceivedObject() { }
    public ReceivedObject(String __by, String __from, FIPA.DateTime __date, String __id, String __via) {
	by = __by;
	from = __from;
	date = __date;
	id = __id;
	via = __via;
    }
}
