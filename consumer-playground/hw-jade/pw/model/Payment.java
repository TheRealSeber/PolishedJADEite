package pw.model;

import java.io.Serializable;
import java.util.Objects;

public final class Payment implements Serializable {

    private static final long serialVersionUID = 1L;

    private final int amountEur;

    public Payment(int amountEur) {
        this.amountEur = amountEur;
    }

    public int amountEur() { return amountEur; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof Payment)) return false;
        return amountEur == ((Payment) o).amountEur;
    }

    @Override
    public int hashCode() {
        return Objects.hash(amountEur);
    }

    @Override
    public String toString() {
        return "Payment[amountEur=" + amountEur + "]";
    }
}