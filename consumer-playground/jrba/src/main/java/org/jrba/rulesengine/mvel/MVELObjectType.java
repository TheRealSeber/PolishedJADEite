package org.jrba.rulesengine.mvel;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Enum describing extended types of objects mapped to actual Java entities
 */
public enum MVELObjectType {

	CONCURRENT_MAP,
	MAP,
	LIST,
	SET;

	/**
	 * Method maps object type to initialized Java object
	 *
	 * @param type type of Java object
	 * @return Java object
	 */
	public static Object getObjectForType(final MVELObjectType type) {
		return switch (type) {
			case CONCURRENT_MAP -> new ConcurrentHashMap<>();
			case MAP -> new HashMap<>();
			case LIST -> new ArrayList<>();
			case SET -> new HashSet<>();
		};
	}
}
