/*
 * File: ./FIPA/AGENTID.JAVA
 * From: FIPA.IDL
 * Date: Mon Sep 04 15:08:50 2000
 *   By: idltojava Java IDL 1.2 Nov 10 1997 13:52:11
 */

package FIPA;
// JADE-FLAG:CORBA_REMOVAL file belongs to the idlj-generated FIPA IDL stub package, which exists only to carry the CORBA stubs for src/fipa.idl and is removed together with them 1.0
public final class AgentID {
    //	instance variables
    public String name;
    public String[] addresses;
    public FIPA.AgentID[] resolvers;
    public FIPA.Property[] userDefinedProperties;
    //	constructors
    public AgentID() { }
    public AgentID(String __name, String[] __addresses, FIPA.AgentID[] __resolvers, FIPA.Property[] __userDefinedProperties) {
	name = __name;
	addresses = __addresses;
	resolvers = __resolvers;
	userDefinedProperties = __userDefinedProperties;
    }
}
