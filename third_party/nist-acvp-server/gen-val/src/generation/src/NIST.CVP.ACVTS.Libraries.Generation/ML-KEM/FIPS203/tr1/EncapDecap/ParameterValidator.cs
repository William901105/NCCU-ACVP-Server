using System.Collections.Generic;
using System.Linq;
using NIST.CVP.ACVTS.Libraries.Common;
using NIST.CVP.ACVTS.Libraries.Common.Helpers;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.PQC.Enums;
using NIST.CVP.ACVTS.Libraries.Crypto.Common.PQC.MLKEM;
using NIST.CVP.ACVTS.Libraries.Generation.Core;

namespace NIST.CVP.ACVTS.Libraries.Generation.ML_KEM.FIPS203.tr1.EncapDecap;

public class ParameterValidator : ParameterValidatorBase, IParameterValidator<Parameters>
{
    public static readonly MLKEMParameterSet[] VALID_PARAMETER_SETS = EnumHelpers.GetEnums<MLKEMParameterSet>().Except([MLKEMParameterSet.None]).ToArray();
    public static readonly MLKEMFunction[] VALID_FUNCTIONS = EnumHelpers.GetEnums<MLKEMFunction>().Except([MLKEMFunction.None]).ToArray();
    public static readonly PrivateKeyFormat[] VALID_KEY_FORMAT = EnumHelpers.GetEnums<PrivateKeyFormat>().Except([PrivateKeyFormat.None]).ToArray();
    
    public ParameterValidateResponse Validate(Parameters parameters)
    {
        var errors = new List<string>();

        ValidateAlgoMode(parameters, [AlgoMode.ML_KEM_EncapDecap_FIPS203_tr1], errors);

        if (parameters.ParameterSets == null)
        {
            errors.Add($"{nameof(parameters.ParameterSets)} was not provided.");
            return new ParameterValidateResponse(errors);
        }
        
        if (!parameters.ParameterSets.Distinct().Any() || !parameters.ParameterSets.Distinct().All(parameterSet => VALID_PARAMETER_SETS.Contains(parameterSet)))
        {
            errors.Add("Expected at least one valid ML-KEM parameter set");
        }
        
        if (parameters.Functions == null)
        {
            errors.Add($"{nameof(parameters.Functions)} was not provided.");
            return new ParameterValidateResponse(errors);
        }
        
        if (!parameters.Functions.Distinct().Any() || !parameters.Functions.Distinct().All(function => VALID_FUNCTIONS.Contains(function)))
        {
            errors.Add("Expected at least one valid ML-KEM function");
        }
        
        if (parameters.Functions.Contains(MLKEMFunction.Decapsulation))
        {
            if (parameters.KeyFormats == null)
            {
                errors.Add($"{nameof(parameters.KeyFormats)} was not provided.");
                return new ParameterValidateResponse(errors);
            }
            
            if (!parameters.KeyFormats.Distinct().Any() ||
                !parameters.KeyFormats.Distinct().All(format => VALID_KEY_FORMAT.Contains(format)))
            {
                errors.Add("Expected at least one valid ML-KEM key format (seed or expanded)");
            }
        }

        if (errors.Any())
        {
            return new ParameterValidateResponse(errors);
        }

        return new ParameterValidateResponse();
    }
}
