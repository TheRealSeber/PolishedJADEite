package jade.core.messaging;

//#J2ME_EXCLUDE_FILE

import java.util.ArrayList;
import java.util.List;

public class MultipleGenericMessage extends GenericMessage {

	private List<GenericMessage> messages = new ArrayList<GenericMessage>(); 
// JADE-FLAG:DIAMOND_OPERATOR Java 7 introduced type inference for generic instance creation: the explicit type arguments of a constructor call may be replaced by <> when the compiler can infer them from context. HIGH
	private int length; // Raw estimation of bytes taken by this MGM
	
	public MultipleGenericMessage(int length) {
		this.length = length;
	}
	
	public List<GenericMessage> getMessages() {
		return messages;
	}
	
	public void setMessages(List<GenericMessage> messages) {
		this.messages = messages;
	}
	
	@Override
	public int getMessagesCnt() {
		return messages.size();
	}
	
	@Override
	public int length() {
		return length;
	}
}
