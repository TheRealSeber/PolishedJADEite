package org.jrba.exception;

/**
 * Exception thrown when system cannot find an agent with given name
 */
public class CannotFindAgentException extends RuntimeException {

	private static final String NO_AGENT_FOUND = "Couldn't find an agent with given name.";

	/**
	 * Default constructor.
	 */
	public CannotFindAgentException() {
		super(NO_AGENT_FOUND);
	}
}
