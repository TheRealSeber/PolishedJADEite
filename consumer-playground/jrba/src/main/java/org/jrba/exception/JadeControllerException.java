package org.jrba.exception;

/**
 * Exception thrown when JADE agent controller couldn't be created
 */
public class JadeControllerException extends RuntimeException {

	/**
	 * Default constructor.
	 *
	 * @param message   error message that is to be displayed
	 * @param exception parent exception
	 */
	public JadeControllerException(String message, Exception exception) {
		super(message, exception);
	}
}
