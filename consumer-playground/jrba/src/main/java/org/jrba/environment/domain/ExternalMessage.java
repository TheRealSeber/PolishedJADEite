package org.jrba.environment.domain;

/**
 * Basic message received from the environment.
 */
public interface ExternalMessage {

	/**
	 * @return message type
	 */
	String getType();
}
