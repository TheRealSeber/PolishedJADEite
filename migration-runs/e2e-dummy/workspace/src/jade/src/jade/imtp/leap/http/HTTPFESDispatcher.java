package jade.imtp.leap.http;

//#J2ME_EXCLUDE_FILE

import jade.imtp.leap.JICP.Connection;
import jade.mtp.TransportAddress;

/**
 *
 * @author Eduard Drenth: Logica, 30-sep-2009
 * 
 */
public class HTTPFESDispatcher extends HTTPFEDispatcher {
// JADE-FLAG:DUMMY_TEST_RULE Dummy pattern HIGH

    protected Connection getConnection(TransportAddress ta) {
        return new HTTPSClientConnection(ta);
    }


}
