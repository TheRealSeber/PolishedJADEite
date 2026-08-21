package org.jrba.exception;

/**
 * Exception thrown when content of messages exchanged between agents is incorrect
 */
public class IncorrectMessageContentException extends RuntimeException {

	private static final String INCORRECT_MESSAGE_FORMAT = "The provided message content has incorrect format";

	/**
	 * Default constructor.
	 */
	public IncorrectMessageContentException() {
		super(INCORRECT_MESSAGE_FORMAT);
	}

}
