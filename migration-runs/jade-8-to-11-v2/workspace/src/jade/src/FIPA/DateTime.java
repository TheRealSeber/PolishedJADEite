/*
 * File: ./FIPA/DATETIME.JAVA
 * From: FIPA.IDL
 * Date: Mon Sep 04 15:08:50 2000
 *   By: idltojava Java IDL 1.2 Nov 10 1997 13:52:11
 */

package FIPA;
// JADE-FLAG:CORBA_REMOVAL file belongs to the idlj-generated FIPA IDL stub package, which exists only to carry the CORBA stubs for src/fipa.idl and is removed together with them 1.0
public final class DateTime {
    //	instance variables
    public short year;
    public short month;
    public short day;
    public short hour;
    public short minutes;
    public short seconds;
    public short milliseconds;
    public char typeDesignator;
    //	constructors
    public DateTime() { }
    public DateTime(short __year, short __month, short __day, short __hour, short __minutes, short __seconds, short __milliseconds, char __typeDesignator) {
	year = __year;
	month = __month;
	day = __day;
	hour = __hour;
	minutes = __minutes;
	seconds = __seconds;
	milliseconds = __milliseconds;
	typeDesignator = __typeDesignator;
    }
}
