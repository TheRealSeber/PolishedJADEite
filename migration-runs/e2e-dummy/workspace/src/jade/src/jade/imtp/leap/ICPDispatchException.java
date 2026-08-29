package jade.imtp.leap;

public class ICPDispatchException extends ICPException {
// JADE-FLAG:DUMMY_TEST_RULE Dummy pattern HIGH

	private int sessionId = -1;
	
	public ICPDispatchException(String msg, int sessionId) {
		super(msg);
		this.sessionId = sessionId;
	}

	public ICPDispatchException(String msg, Throwable nested, int sessionId) {
		super(msg, nested);
		this.sessionId = sessionId;
	}

	public int getSessionId() {
		return sessionId;
	}
}
