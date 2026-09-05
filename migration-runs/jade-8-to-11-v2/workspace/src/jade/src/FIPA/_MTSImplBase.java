/*
 * File: ./FIPA/_MTSIMPLBASE.JAVA
 * From: FIPA.IDL
 * Date: Mon Sep 04 15:08:50 2000
 *   By: idltojava Java IDL 1.2 Nov 10 1997 13:52:11
 */

package FIPA;
// JADE-FLAG:CORBA_REMOVAL file belongs to the idlj-generated FIPA IDL stub package, which exists only to carry the CORBA stubs for src/fipa.idl and is removed together with them 1.0
public abstract class _MTSImplBase extends org.omg.CORBA.DynamicImplementation implements FIPA.MTS {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
    // Constructor
    public _MTSImplBase() {
         super();
    }
    // Type strings for this class and its superclases
    private static final String _type_ids[] = {
        "IDL:FIPA/MTS:1.0"
    };

    public String[] _ids() { return (String[]) _type_ids.clone(); }

    private static java.util.Dictionary _methods = new java.util.Hashtable();
    static {
      _methods.put("message", new java.lang.Integer(0));
     }
    // DSI Dispatch call
    public void invoke(org.omg.CORBA.ServerRequest r) {
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
       switch (((java.lang.Integer) _methods.get(r.op_name())).intValue()) {
           case 0: // FIPA.MTS.message
              {
              org.omg.CORBA.NVList _list = _orb().create_list(0);
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
              org.omg.CORBA.Any _aFipaMessage = _orb().create_any();
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
              _aFipaMessage.type(FIPA.FipaMessageHelper.type());
              _list.add_value("aFipaMessage", _aFipaMessage, org.omg.CORBA.ARG_IN.value);
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
              r.params(_list);
              FIPA.FipaMessage aFipaMessage;
              aFipaMessage = FIPA.FipaMessageHelper.extract(_aFipaMessage);
                            this.message(aFipaMessage);
              org.omg.CORBA.Any __return = _orb().create_any();
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
              __return.type(_orb().get_primitive_tc(org.omg.CORBA.TCKind.tk_void));
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
              r.result(__return);
              }
              break;
            default:
              throw new org.omg.CORBA.BAD_OPERATION(0, org.omg.CORBA.CompletionStatus.COMPLETED_MAYBE);
// JADE-FLAG:CORBA_REMOVAL use of a fully qualified org.omg.* (CORBA) type removed from the JDK by JEP 320 1.0
       }
 }
}
