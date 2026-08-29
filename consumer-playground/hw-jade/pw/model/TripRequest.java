package pw.model;

import java.io.Serializable;
import java.time.LocalDate;
import java.util.Objects;

public final class TripRequest implements Serializable {

    private static final long serialVersionUID = 1L;

    private final String fromCity;
    private final String toCity;
    private final LocalDate departDate;
    private final LocalDate returnDate;

    public TripRequest(String fromCity, String toCity, LocalDate departDate, LocalDate returnDate) {
        this.fromCity = fromCity;
        this.toCity = toCity;
        this.departDate = departDate;
        this.returnDate = returnDate;
    }

    public String fromCity() { return fromCity; }
    public String toCity() { return toCity; }
    public LocalDate departDate() { return departDate; }
    public LocalDate returnDate() { return returnDate; }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (!(o instanceof TripRequest)) return false;
        TripRequest that = (TripRequest) o;
        return Objects.equals(fromCity, that.fromCity)
                && Objects.equals(toCity, that.toCity)
                && Objects.equals(departDate, that.departDate)
                && Objects.equals(returnDate, that.returnDate);
    }

    @Override
    public int hashCode() {
        return Objects.hash(fromCity, toCity, departDate, returnDate);
    }

    @Override
    public String toString() {
        return "TripRequest[fromCity=" + fromCity + ", toCity=" + toCity
                + ", departDate=" + departDate + ", returnDate=" + returnDate + "]";
    }
}