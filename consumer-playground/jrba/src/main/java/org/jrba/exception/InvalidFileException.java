package org.jrba.exception;

/**
 * Exception thrown when the system cannot read a file
 */
public class InvalidFileException extends RuntimeException {

	/**
	 * Default constructor.
	 *
	 * @param message error message that is to be displayed.
	 */
	public InvalidFileException(final String message) {
		super(message);
	}

}
