package pw.model;

import java.io.Serializable;

public record Payment(int amountEur) implements Serializable {
}