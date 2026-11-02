using System;
class SharedScrollChecks {
    static void Require(bool condition,string message){if(!condition)throw new Exception(message);}
    static void Invalid(double value,double minimum,double maximum) {
        bool failed=false;try{ScrollAccess.Percent(value,minimum,maximum);}catch{failed=true;}
        Require(failed,"Unverifiable ranges must be refused");
    }
    static void Main() {
        Require(ScrollAccess.Percent(10,10,90)==0,"start boundary");
        Require(ScrollAccess.Percent(90,10,90)==100,"end boundary");
        Require(ScrollAccess.Percent(50,10,90)==50,"nonzero range origins");
        Require(ScrollAccess.Close(-1,-1),"unused axes");
        Require(!ScrollAccess.Close(-1,25),"missing position is not success");
        Require(!ScrollAccess.Close(0,25),"no movement cannot verify a distant target");
        Require(ScrollAccess.Close(24.8,25),"provider rounding tolerance");
        Require(!ScrollAccess.ViewMatches(93.08641975,39.29236499),"loading viewport cannot authorize scrolling");
        Require(ScrollAccess.ViewMatches(39.29236499,39.29236499),"loaded recorded viewport");
        Require(!ScrollAccess.ViewMatches(null,39.29236499),"missing viewport cannot verify readiness");
        Require(!ScrollAccess.ViewMatches(Double.NaN,39.29236499),"non-finite viewport cannot verify readiness");
        Invalid(Double.NaN,0,100);Invalid(Double.PositiveInfinity,0,100);
        Invalid(1,1,1);Invalid(100,10,90);
        Console.WriteLine("PASS 15 shared scroll range/viewport checks (no desktop input)");
    }
}
